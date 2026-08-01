from pathlib import Path
import json
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
MODEL_JS = ROOT / "assets" / "candidate-signals.js"
WORKSPACE_JS = ROOT / "assets" / "candidate-signals-workspace.js"
WORKSPACE_CSS = ROOT / "assets" / "candidate-signals.css"
HYBRID_JS = ROOT / "assets" / "hybrid-dashboard.js"
CANDIDATE_JSON = ROOT / "candidate_signals.json"


def candidate(candidate_id, name, development_url="https://example.test/item"):
    return {
        "candidate_id": candidate_id,
        "candidate_name": name,
        "polling": {
            "evidence_state": "reported",
            "hypothesis_count": 2,
            "range_min": 0,
            "range_max": 6,
            "selected_hypothesis_score": 0,
            "selected_hypothesis_rank": 4,
        },
        "campaign_attention": {
            "evidence_state": "reported",
            "record_count": 0,
            "share": 0,
            "publisher_count": 2,
            "active_day_count": 3,
            "headline_match_count": 0,
            "summary_only_match_count": 0,
            "scope_counts": {"campaign": 0, "election": 2, "general": 1},
            "scope_shares": {"campaign": 0, "election": 0.667, "general": 0.333},
            "story_cluster_count": 2,
            "concentration": {
                "leading_publisher": "Example",
                "leading_publisher_record_count": 1,
                "leading_publisher_share": 0.5,
                "leading_story_record_count": 1,
                "leading_story_share": 0.5,
            },
        },
        "general_visibility": {
            "evidence_state": "reported",
            "record_count": 1,
            "share": 0.25,
            "publisher_count": 1,
            "active_day_count": 1,
            "headline_match_count": 1,
            "summary_only_match_count": 0,
            "story_cluster_count": 1,
            "concentration": {
                "leading_publisher": "General Example",
                "leading_publisher_record_count": 1,
                "leading_publisher_share": 1,
                "leading_story_record_count": 1,
                "leading_story_share": 1,
            },
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
                "review_count": 3,
                "by_count": 1,
                "about_count": 2,
                "newest_review_date": "2026-07-17",
                "newest_review_url": "https://example.test/review",
            },
        },
        "latest_development": {
            "evidence_state": "reported",
            "id": f"development-{candidate_id}",
            "published_at": "2026-07-29T12:00:00Z",
            "publisher": "Example Publisher",
            "headline": f"Development for {name}",
            "url": development_url,
            "coverage_scope": "campaign",
        },
    }


def payload(rows):
    return {
        "schema_version": "1.0",
        "candidate_universe": {"count": len(rows)},
        "featured_polling_package": {
            "pollster": "Example Pollster",
            "fieldwork_start": "2026-07-09",
            "fieldwork_end": "2026-07-10",
            "sample_size": 1503,
            "hypothesis_count": 2,
            "source_urls": ["https://example.test/poll"],
        },
        "candidates": json.loads(json.dumps(rows)),
    }


def run_workspace(input_payload, selected_id=None, action=None):
    script = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));

function dataKey(name) {
  return name.slice(5).replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
}

class MiniNode {
  constructor(tagName) {
    this.tagName = String(tagName).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attributes = {};
    this.dataset = {};
    this.className = "";
    this.style = {};
    this._text = "";
    this._listeners = {};
    this.scope = "";
  }
  set textContent(value) {
    this._text = String(value ?? "");
    this.children = [];
  }
  get textContent() {
    return this._text + this.children.map(child => child.textContent).join("");
  }
  append(...nodes) {
    nodes.forEach(node => {
      if (node === null || node === undefined) return;
      node.parentNode = this;
      this.children.push(node);
    });
  }
  replaceChildren(...nodes) {
    this.children = [];
    this._text = "";
    this.append(...nodes);
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name.startsWith("data-")) this.dataset[dataKey(name)] = String(value);
  }
  getAttribute(name) {
    return this.attributes[name];
  }
  addEventListener(type, listener) {
    (this._listeners[type] ||= []).push(listener);
  }
  dispatch(type, values = {}) {
    const event = {
      key: values.key,
      defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; }
    };
    (this._listeners[type] || []).forEach(listener => listener(event));
    return event;
  }
  focus() {
    documentObject.activeElement = this;
  }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children =
      this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }
  matches(selector) {
    if (selector.startsWith(".")) {
      return this.className.split(/\s+/).includes(selector.slice(1));
    }
    return this.tagName === selector.toUpperCase();
  }
  querySelectorAll(selector) {
    const result = [];
    const visit = node => {
      node.children.forEach(child => {
        if (child.matches(selector)) result.push(child);
        visit(child);
      });
    };
    visit(this);
    return result;
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

const documentObject = {
  activeElement: null,
  createElement(tagName) { return new MiniNode(tagName); }
};
const windowObject = {};
const context = {
  window: windowObject,
  document: documentObject,
  URL,
  Object,
  Array,
  Set,
  Map,
  Number,
  String,
  Math,
  Promise
};
vm.runInNewContext(fs.readFileSync("assets/candidate-signals.js", "utf8"), context);
vm.runInNewContext(fs.readFileSync("assets/candidate-signals-workspace.js", "utf8"), context);

const state = windowObject.France2027CandidateSignals.normalize(input.payload);
const api = windowObject.France2027CandidateSignalsWorkspace;
const mount = new MiniNode("div");
let selected = input.selectedId;
let selectCalls = [];
function renderCurrent() {
  return api.render(mount, state, {
    selectedCandidateId: selected,
    onSelect(candidateId) {
      selectCalls.push(candidateId);
      selected = candidateId;
      renderCurrent();
    },
    resolvePortrait(candidateId) {
      return `assets/candidates/${candidateId}.png`;
    }
  });
}
let resolved = renderCurrent();

if (input.action === "click-second") {
  mount.querySelectorAll(".candidate-signals-candidate-button")[1].dispatch("click");
  resolved = selected;
}
if (input.action === "end-from-first") {
  mount.querySelectorAll(".candidate-signals-candidate-button")[0]
    .dispatch("keydown", { key: "End" });
  resolved = selected;
}

function details() {
  const buttons = mount.querySelectorAll(".candidate-signals-candidate-button");
  const links = mount.querySelectorAll(".candidate-signals-source-link");
  const workspace = mount.querySelector(".candidate-signals-workspace");
  const allNodes = [];
  const visit = node => {
    allNodes.push(node);
    node.children.forEach(visit);
  };
  visit(mount);
  return {
    apiKeys: Object.keys(api),
    apiFrozen: Object.isFrozen(api),
    resolved,
    status: mount.getAttribute("data-candidate-signals-state"),
    text: mount.textContent,
    tags: allNodes.map(node => node.tagName),
    candidateOrder: buttons.map(button => button.dataset.candidateSignalsCandidate),
    pressed: buttons.map(button => button.getAttribute("aria-pressed")),
    primaryOrder: workspace
      ? workspace.children.map(node => node.className)
      : [],
    regionTitles: mount.querySelectorAll(".candidate-signals-region-title")
      .map(node => node.textContent),
    analysisCardTitles:
      mount.querySelectorAll(".candidate-signals-analysis-card-title")
        .map(node => node.textContent),
    dossierCardTitles:
      mount.querySelectorAll(".candidate-signals-dossier-card-title")
        .map(node => node.textContent),
    candidacyStatus:
      mount.querySelectorAll(".candidate-signals-candidacy-status")
        .map(node => node.textContent),
    monitorListCount:
      mount.querySelectorAll(".candidate-signals-monitor-list").length,
    latestAnalysisCount:
      mount.querySelectorAll(".candidate-signals-latest-development").length,
    latestDossierCount:
      mount.querySelectorAll(".candidate-signals-dossier-development").length,
    buttonCount: buttons.length,
    linkHrefs: links.map(link => link.href),
    linkTargets: links.map(link => link.target),
    linkRels: links.map(link => link.rel),
    selectCalls,
    focusedCandidate: documentObject.activeElement
      ? documentObject.activeElement.dataset.candidateSignalsCandidate || null
      : null
  };
}
process.stdout.write(JSON.stringify(details()));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(
            {
                "payload": input_payload,
                "selectedId": selected_id,
                "action": action,
            }
        ),
        cwd=ROOT,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


class CandidateSignalsWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.model_js = MODEL_JS.read_text(encoding="utf-8")
        cls.workspace_js = WORKSPACE_JS.read_text(encoding="utf-8")
        cls.css = WORKSPACE_CSS.read_text(encoding="utf-8")
        cls.hybrid_js = HYBRID_JS.read_text(encoding="utf-8")
        cls.rows = [
            candidate("zeta", "Zeta Candidate"),
            candidate("alpha", "Alpha Candidate"),
            candidate("middle", "Middle Candidate"),
        ]

    def test_workspace_assets_exist_and_load_in_required_order(self):
        self.assertTrue(WORKSPACE_JS.is_file())
        self.assertTrue(WORKSPACE_CSS.is_file())
        shell = '<link rel="stylesheet" href="assets/final-dashboard-shell.css">'
        css = '<link rel="stylesheet" href="assets/candidate-signals.css">'
        model = '<script src="assets/candidate-signals.js"></script>'
        workspace = '<script src="assets/candidate-signals-workspace.js"></script>'
        dashboard = '<script src="assets/hybrid-dashboard.js"></script>'
        self.assertLess(self.html.index(shell), self.html.index(css))
        self.assertLess(self.html.index(model), self.html.index(workspace))
        self.assertLess(self.html.index(workspace), self.html.index(dashboard))

    def test_frozen_namespace_exposes_exactly_render(self):
        result = run_workspace(payload(self.rows))
        self.assertEqual(result["apiKeys"], ["render"])
        self.assertTrue(result["apiFrozen"])
        self.assertIn(
            "window.France2027CandidateSignalsWorkspace = Object.freeze({",
            self.workspace_js,
        )

    def test_renderer_never_fetches_and_dashboard_fetches_exactly_once(self):
        self.assertNotIn("fetch(", self.workspace_js)
        self.assertNotIn("candidate_signals.json", self.workspace_js)
        self.assertEqual(
            self.hybrid_js.count('.load("candidate_signals.json")'),
            1,
        )

    def test_normalized_source_order_and_default_selection(self):
        result = run_workspace(payload(self.rows))
        expected = ["zeta", "alpha", "middle"]
        self.assertEqual(result["candidateOrder"], expected)
        self.assertEqual(result["resolved"], "zeta")
        self.assertEqual(result["pressed"], ["true", "false", "false"])
        self.assertNotIn(".sort(", self.workspace_js)

    def test_only_active_main_and_secondary_candidates_are_rendered(self):
        published = json.loads(
            CANDIDATE_JSON.read_text(encoding="utf-8")
        )
        result = run_workspace(published)

        active_ids = {
            *published["presidential_field"]["main"],
            *published["presidential_field"]["secondary"],
        }
        expected = [
            candidate["candidate_id"]
            for candidate in published["candidates"]
            if candidate["candidate_id"] in active_ids
        ]

        self.assertEqual(
            len(expected),
            published["presidential_field"]["counts"]["active"],
        )
        self.assertEqual(len(result["candidateOrder"]), 18)
        self.assertEqual(result["candidateOrder"], expected)
        self.assertEqual(result["monitorListCount"], 1)
        self.assertFalse(
            set(published["presidential_field"]["hidden"])
            & set(result["candidateOrder"])
        )

    def test_valid_active_selection_is_preserved_and_hidden_falls_back(self):
        published = json.loads(
            CANDIDATE_JSON.read_text(encoding="utf-8")
        )
        active_set = {
            *published["presidential_field"]["main"],
            *published["presidential_field"]["secondary"],
        }
        active_ids = [
            candidate["candidate_id"]
            for candidate in published["candidates"]
            if candidate["candidate_id"] in active_set
        ]
        preserved_id = active_ids[-1]
        hidden_id = published["presidential_field"]["hidden"][0]

        preserved = run_workspace(published, preserved_id)
        hidden = run_workspace(published, hidden_id)
        invalid = run_workspace(published, "missing")

        self.assertEqual(preserved["resolved"], preserved_id)
        self.assertEqual(len(preserved["pressed"]), 18)
        self.assertEqual(hidden["resolved"], active_ids[0])
        self.assertEqual(invalid["resolved"], active_ids[0])
        self.assertEqual(hidden["pressed"][0], "true")
        self.assertNotIn(hidden_id, hidden["candidateOrder"])

    def test_selection_updates_dossier_without_reordering(self):
        result = run_workspace(payload(self.rows), action="click-second")
        self.assertEqual(result["resolved"], "alpha")
        self.assertEqual(result["selectCalls"], ["alpha"])
        self.assertEqual(result["candidateOrder"], ["zeta", "alpha", "middle"])
        self.assertIn("Development for Alpha Candidate", result["text"])
        self.assertNotIn("Development for Zeta Candidate", result["text"])
        integration = self.hybrid_js[
            self.hybrid_js.index("  function renderCandidateSignalsPanel()") :
            self.hybrid_js.index("  function setActiveSignalView(")
        ]
        self.assertIn("renderCandidateSignalsPanel();", integration)
        self.assertNotIn("renderAll();", integration)

    def test_exact_three_column_order_and_no_old_matrix(self):
        result = run_workspace(payload(self.rows))
        self.assertEqual(
            result["regionTitles"],
            [
                "CANDIDATE MONITOR",
                "SELECTED ANALYSIS",
                "CANDIDATE DOSSIER",
            ],
        )
        self.assertEqual(
            result["primaryOrder"],
            [
                "candidate-signals-panel candidate-signals-monitor",
                "candidate-signals-panel candidate-signals-analysis",
                "candidate-signals-panel candidate-signals-dossier",
            ],
        )
        self.assertNotIn("EVIDENCE MATRIX", result["text"])
        self.assertNotIn(
            "Candidate evidence will be rendered in the next implementation stage.",
            self.html + self.hybrid_js + self.workspace_js,
        )

    def test_one_candidate_list_uses_real_buttons_and_explicit_state(self):
        result = run_workspace(payload(self.rows))
        self.assertEqual(result["monitorListCount"], 1)
        self.assertEqual(result["buttonCount"], 3)
        self.assertEqual(result["tags"].count("BUTTON"), 5)
        self.assertIn("View full evidence →", result["text"])
        self.assertNotIn("TABLE", result["tags"])
        self.assertIn('button.setAttribute("aria-pressed", String(selected));', self.workspace_js)
        self.assertNotIn('selected ? "SELECTED" : "SELECT"', self.workspace_js)
        self.assertNotIn(
            "candidate-signals-selection-label",
            self.workspace_js,
        )

    def test_candidate_keyboard_contract_selects_and_restores_focus(self):
        result = run_workspace(payload(self.rows), action="end-from-first")
        self.assertEqual(result["resolved"], "middle")
        self.assertEqual(result["selectCalls"], ["middle"])
        self.assertEqual(result["focusedCandidate"], "middle")
        for key in ("ArrowDown", "ArrowUp", "Home", "End"):
            self.assertIn(f'event.key === "{key}"', self.workspace_js)
        self.assertIn("event.preventDefault();", self.workspace_js)

    def test_loading_ready_empty_and_unavailable_presentations(self):
        cases = [
            (
                {"schema_version": "1.0", "candidates": []},
                "empty",
                "No candidate evidence is currently published.",
                False,
            ),
            (
                {"schema_version": "2.0", "candidates": []},
                "unavailable",
                "Candidate evidence is temporarily unavailable.",
                False,
            ),
        ]
        for source, status, message, has_workspace in cases:
            with self.subTest(status=status):
                result = run_workspace(source)
                self.assertEqual(result["status"], status)
                self.assertIn(message, result["text"])
                self.assertEqual(
                    "CANDIDATE MONITOR" in result["text"],
                    has_workspace,
                )

        ready = run_workspace(payload(self.rows))
        self.assertEqual(ready["status"], "ready")
        self.assertIn("CANDIDATE MONITOR", ready["text"])
        self.assertIn("Loading candidate evidence…", self.workspace_js)
        self.assertIn('node.setAttribute("role", "status");', self.workspace_js)
        self.assertNotIn("state.reason", self.workspace_js)

    def test_desktop_tablet_and_mobile_geometry(self):
        desktop_start = self.css.index("@media (min-width: 1180px)")
        tablet_start = self.css.index(
            "@media (min-width: 760px) and (max-width: 1179px)"
        )
        mobile_start = self.css.index("@media (max-width: 759px)")

        base = self.css[:desktop_start]
        desktop = self.css[desktop_start:tablet_start]
        tablet = self.css[tablet_start:mobile_start]
        mobile = self.css[mobile_start:]

        for token in (
            "minmax(0, 27fr)",
            "minmax(0, 36fr)",
            "minmax(0, 37fr)",
            "align-items: stretch;",
            "align-self: stretch;",
        ):
            self.assertIn(token, desktop)

        self.assertIn("overflow: visible;", base)
        self.assertIn("position: relative;", desktop)
        self.assertIn("height: 430px;", desktop)
        self.assertIn("max-height: 430px;", desktop)
        self.assertIn("overflow-y: auto;", desktop)
        self.assertIn("overscroll-behavior: contain;", desktop)
        self.assertNotIn("position: sticky;", desktop)
        self.assertIn("max-height:", desktop)
        self.assertNotIn("height: 460px;", self.css)
        self.assertNotIn("height: 620px;", self.css)
        self.assertNotIn("height: 360px;", self.css)

        self.assertIn(
            "grid-template-columns: minmax(0, 38fr) minmax(0, 62fr);",
            tablet,
        )
        self.assertIn(".candidate-signals-analysis", tablet)
        self.assertIn(".candidate-signals-dossier", tablet)

        self.assertIn(
            "grid-template-columns: minmax(0, 1fr);",
            mobile,
        )
        self.assertIn("position: static;", mobile)
        self.assertEqual(self.workspace_js.count("candidateMonitor("), 2)
        self.assertNotIn('createElement("table"', self.workspace_js)

    def test_candidate_monitor_has_internal_vertical_scroll_only(self):
        monitor_start = self.css.index(".candidate-signals-monitor-list {")
        monitor_end = self.css.index("}", monitor_start)
        monitor_rule = self.css[monitor_start:monitor_end]

        self.assertIn("overflow-x: hidden;", monitor_rule)
        self.assertIn("overflow-y: auto;", monitor_rule)
        self.assertIn(
            ".candidate-signals-analysis-body,\n"
            ".candidate-signals-dossier-body {",
            self.css,
        )
        body_start = self.css.index(".candidate-signals-analysis-body,\n")
        body_end = self.css.index("}", body_start)
        body_rule = self.css[body_start:body_end]
        self.assertIn("overflow: visible;", body_rule)
        self.assertNotIn("overflow-y: auto;", body_rule)

    def test_dossier_sections_have_exact_required_order(self):
        result = run_workspace(payload(self.rows))

        self.assertEqual(
            result["dossierCardTitles"],
            [
                "VISIBILITY & COMPOSITION",
                "EVIDENCE STRUCTURE",
                "SCRUTINY OVERVIEW",
                "LATEST DEVELOPMENT",
            ],
        )
        self.assertIn("View full evidence details", result["text"])
        self.assertIn("POLL EVIDENCE & SOURCE DETAILS", result["text"])
        self.assertIn("Open latest source →", result["text"])
        for required in (
            "function dossierScopeCell(",
            "function dossierStructureRatio(",
            "function dossierScrutinyPeriod(",
            "candidate-signals-dossier-composition-stack",
            "candidate-signals-dossier-scrutiny-grid",
            "candidate-signals-dossier-badges",
        ):
            self.assertIn(required, self.workspace_js)
        for required in (
            ".candidate-signals-dossier-composition-stack {",
            ".candidate-signals-dossier-scrutiny-grid {",
            ".candidate-signals-dossier-details-content",
            "min-height: 132px;",
            "min-height: 72px;",
        ):
            self.assertIn(required, self.css)
        self.assertNotIn("candidate-signals-dossier-donut", self.workspace_js)
        self.assertNotIn(
            "candidate-signals-dossier-poll",
            self.workspace_js,
        )

    def test_unpublished_fields_are_not_zero_and_published_zero_remains(self):
        source = payload(self.rows)
        source["candidates"][0]["general_visibility"] = None
        result = run_workspace(source)
        self.assertIn("Not published", result["text"])
        self.assertIn("Point estimate0%", result["text"])
        self.assertIn("Campaign / election0 records · 0%", result["text"])

        range_only = payload(self.rows)
        range_only["candidates"][0]["polling"][
            "selected_hypothesis_score"
        ] = None
        range_result = run_workspace(range_only)
        self.assertIn("Point estimateRange only", range_result["text"])

    def test_visibility_composition_and_scrutiny_dimensions_remain_separate(self):
        result = run_workspace(payload(self.rows))
        text = result["text"]
        for label in (
            "Campaign / election",
            "General visibility",
            "Campaign",
            "Election",
            "General",
            "14 days · BY",
            "14 days · ABOUT",
            "Archive · BY",
            "Archive · ABOUT",
        ):
            self.assertIn(label, text)
        self.assertNotIn("claim row", self.workspace_js.lower())

    def test_selected_analysis_has_exact_four_cards(self):
        result = run_workspace(payload(self.rows))

        self.assertEqual(
            result["analysisCardTitles"],
            [
                "POLL EVIDENCE",
                "CAMPAIGN ATTENTION",
                "COVERAGE MIX",
                "SCRUTINY",
            ],
        )
        for required in (
            "function pollSummaryCard(candidate, metadata)",
            "function attentionSummaryCard(candidate)",
            "function scopeCompositionCard(candidate)",
            "function scrutinySummaryCard(candidate)",
            "function evidenceStructureBreakdown(candidate, metadata)",
            "function candidacyEvidence(candidate)",
        ):
            self.assertIn(required, self.workspace_js)

        for label in (
            "EVIDENCE STRUCTURE",
            "Records",
            "Publishers",
            "Active days",
            "Story clusters",
            "Match basis",
            "Top publisher",
            "Top story concentration",
            "CANDIDACY EVIDENCE",
            "ABOUT",
            "BY",
            "REVIEWS",
            "14 DAYS",
            "ARCHIVE",
        ):
            self.assertIn(label, result["text"])

        self.assertIn("2 hypotheses", result["text"])
        self.assertIn("N=1,503", result["text"])
        self.assertIn("PUBLISHED RANGE", result["text"])
        self.assertIn("0 REC · 2 PUB · 3 DAYS", result["text"])
        self.assertIn("Open latest source →", result["text"])
        self.assertNotIn(
            "COVERAGE COMPOSITION · PUBLISHED SCOPE",
            result["text"],
        )

    def test_selected_analysis_uses_comparative_attention_and_signal_states(self):
        source = self.workspace_js

        for required in (
            "const scaleMaximum = publishedShares.length",
            "(share / Number(scaleMaximum)) * 100",
            "candidate-signals-attention-share${",
            '"is-zero"',
            '"is-active"',
            '"is-unpublished"',
            "const basisTotal = published",
            "Number(headline) + Number(summaryOnly)",
            "LATEST REVIEW ·",
            "function groupedNumberText(value)",
            "clamp(4px, ${markerPosition}%, calc(100% - 4px))",
        ):
            self.assertIn(required, source)

        for required in (
            ".candidate-signals-scrutiny-cell.is-zero {",
            ".candidate-signals-scrutiny-cell.is-active {",
            ".candidate-signals-scrutiny-cell.is-archive.is-active {",
            ".candidate-signals-attention-share.is-unpublished {",
        ):
            self.assertIn(required, self.css)

    def test_selected_analysis_uses_candidacy_and_human_dates(self):
        result = run_workspace(payload(self.rows))
        text = result["text"]

        self.assertIn("CANDIDACY EVIDENCE", text)
        self.assertIn(
            "No candidacy evidence is currently published.",
            text,
        )
        self.assertIn("29 Jul 2026", text)
        self.assertNotIn("2026-07-29T12:00:00Z", text)

        published_source = json.loads(
            CANDIDATE_JSON.read_text(encoding="utf-8")
        )
        published_candidate = next(
            item
            for item in published_source["candidates"]
            if item.get("candidacy", {}).get("source_url")
        )
        published = run_workspace(
            published_source,
            published_candidate["candidate_id"],
        )
        published_text = published["text"]
        candidacy = published_candidate["candidacy"]

        expected_status = " ".join(
            word.capitalize()
            for word in str(candidacy["status"]).split("_")
            if word
        )
        self.assertIn(expected_status, published_text)
        self.assertIn(
            str(candidacy["display_tier"]).upper(),
            published_text,
        )
        self.assertIn(candidacy["status_note"], published_text)
        self.assertIn(candidacy["source_publisher"], published_text)
        self.assertIn("View candidacy source →", published_text)

        self.assertNotIn("function snapshotRow(", self.workspace_js)
        self.assertNotIn("candidate-signals-snapshot", self.workspace_js)
        self.assertNotIn("PRIOR", text)
        self.assertNotIn("CURRENT", text)
        self.assertNotIn("delta", self.workspace_js.lower())

    def test_only_published_latest_development_is_presented(self):
        result = run_workspace(payload(self.rows))
        self.assertEqual(result["latestAnalysisCount"], 1)
        self.assertEqual(result["latestDossierCount"], 1)
        self.assertEqual(
            result["text"].count("Development for Zeta Candidate"),
            2,
        )
        self.assertNotIn("RECENT SIGNALS", result["text"])
        self.assertNotIn("View all", result["text"])

    def test_missing_latest_development_uses_exact_empty_copy(self):
        source = payload(self.rows)
        source["candidates"][0]["latest_development"] = None
        result = run_workspace(source)
        self.assertEqual(
            result["text"].count(
                "No source-linked development is currently published."
            ),
            2,
        )
        self.assertEqual(result["linkHrefs"], [])

    def test_dossier_retains_supported_poll_provenance(self):
        result = run_workspace(payload(self.rows))
        for label in (
            "PollsterExample Pollster",
            "Field dates9–10 Jul 2026",
            "Sample1,503",
            "Hypotheses2",
            "Published sources1",
        ):
            self.assertIn(label, result["text"])

    def test_evidence_breadth_and_concentration_are_neutral(self):
        result = run_workspace(payload(self.rows))
        for label in (
            "CAMPAIGN / ELECTION STRUCTURE",
            "GENERAL STRUCTURE",
            "Publishers",
            "Active days",
            "Story clusters",
            "Publisher concentration",
            "Top publisher",
            "Top story concentration",
        ):
            self.assertIn(label, result["text"])
        self.assertNotRegex(
            result["text"].lower(),
            r"\b(good|bad|strong|weak|broad support|narrow support)\b",
        )

    def test_source_url_accepts_only_http_and_https(self):
        for scheme in ("https://example.test/item", "http://example.test/item"):
            with self.subTest(scheme=scheme):
                result = run_workspace(
                    payload([candidate("one", "One", scheme)])
                )
                self.assertEqual(len(result["linkHrefs"]), 2)
                self.assertEqual(result["linkTargets"], ["_blank", "_blank"])
                self.assertEqual(
                    result["linkRels"],
                    ["noopener noreferrer", "noopener noreferrer"],
                )
        for unsafe in (
            "javascript:alert(1)",
            "data:text/plain,bad",
            "file:///tmp/bad",
            "not a url",
        ):
            with self.subTest(unsafe=unsafe):
                result = run_workspace(
                    payload([candidate("one", "One", unsafe)])
                )
                self.assertEqual(result["linkHrefs"], [])
                self.assertIn("Source linkNot published", result["text"])

    def test_metadata_not_in_contract_is_not_rendered(self):
        source = payload(self.rows)
        source["candidates"][0].update(
            {
                "party": "Forbidden Party",
                "role": "Forbidden Role",
                "ideology": "Forbidden Ideology",
                "status": "Forbidden Status",
            }
        )
        result = run_workspace(source)
        for value in (
            "Forbidden Party",
            "Forbidden Role",
            "Forbidden Ideology",
            "Forbidden Status",
        ):
            self.assertNotIn(value, result["text"])

    def test_no_ranking_inference_or_decorative_chart_code(self):
        source = self.workspace_js.lower()

        for forbidden in (
            "combined_score",
            "viability_score",
            "momentum_score",
            "sentiment_score",
            "forecast",
            "probability",
            ".sort(",
            "canvas",
        ):
            self.assertNotIn(forbidden, source)

        for required in (
            "function pollSummaryCard(candidate, metadata)",
            "function attentionSummaryCard(candidate)",
            "function scopeCompositionCard(candidate)",
            "function scrutinySummaryCard(candidate)",
            "function evidenceStructureBreakdown(candidate, metadata)",
            "function evidenceMatchBasis(candidate)",
            "function candidacyEvidence(candidate)",
            "function dossierVisibilityPanel(candidate)",
            "function evidenceStructurePanel(candidate)",
            "function scrutinyOverviewPanel(candidate)",
            "function compactEvidenceDetails(candidate, metadata)",
        ):
            self.assertIn(required, self.workspace_js)

        self.assertNotIn("conic-gradient", self.workspace_js)
        self.assertNotIn("candidate-signals-dossier-donut", self.workspace_js)
        self.assertIn(
            "candidate-signals-dossier-composition-stack",
            self.workspace_js,
        )
        self.assertIn(
            "candidate-signals-dossier-scrutiny-grid",
            self.workspace_js,
        )
        self.assertIn("candidate-signals-poll-gauge", self.workspace_js)
        self.assertIn("candidate-signals-attention-track", self.workspace_js)
        self.assertIn("candidate-signals-composition-stack", self.workspace_js)
        self.assertIn("candidate-signals-scrutiny-matrix", self.workspace_js)
        self.assertIn(
            'input.setAttribute("aria-controls", '
            '"candidate-signals-monitor-list");',
            self.workspace_js,
        )
        self.assertIn(
            'createElement(\n      "details",\n'
            '      "candidate-signals-dossier-details"',
            self.workspace_js,
        )

    def test_stage3_semantic_rebuild_contract(self):
        for forbidden in (
            "function analysisCard(",
            "function dossierCard(",
            "function compositionLines(",
            "function latestDevelopment(",
            "function coverageCompositionBreakdown(",
        ):
            self.assertNotIn(forbidden, self.workspace_js)

        for required in (
            "function candidateFact(label, value, className = \"\")",
            "function scopeComposition(candidate)",
            "function analysisLatestDevelopment(candidate)",
            "function dossierLatestDevelopment(candidate)",
            "function evidenceStructureBreakdown(candidate, metadata)",
            "function candidacyEvidence(candidate)",
            "candidate-signals-composition-visual",
            "const complete = values.every(value => value !== null);",
            "composition.complete && composition.total > 0",
        ):
            self.assertIn(required, self.workspace_js)

        for required in (
            "min-height: 120px;",
            ".candidate-signals-composition-stack {",
            "height: 12px;",
            "width: 78px;",
            "width: 118px;",
            "min-height: 132px;",
        ):
            self.assertIn(required, self.css)

    def test_stage4_visual_hierarchy_contract(self):
        for required in (
            "function attentionVisualRow(\n    label,\n    evidence,\n    tone,\n    scaleMaximum\n  )",
            "function evidenceStructureStat(label, value)",
            "function evidenceRatioRow(",
            "function evidenceMatchBasis(candidate)",
            "function scrutinyMatrixCell(value, periodClass = \"\")",
            "function candidacyEvidence(candidate)",
            "candidate-signals-composition-visual",
            "candidate-signals-development-meta",
            "function compactPercentageText(value, ratio = false)",
            "function dossierMetric(\n    label,\n    primary,\n    notes = [],\n    className = \"\"\n  )",
            '"Point estimate"',
        ):
            self.assertIn(required, self.workspace_js)

        for forbidden in (
            "candidate-signals-snapshot-track",
            "candidate-signals-snapshot-details",
            "function snapshotRow(",
            "candidate-signals-dossier-subtitle",
        ):
            self.assertNotIn(forbidden, self.workspace_js)

        for required in (
            ".candidate-signals-analysis-cards {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(0, 1fr));",
            ".candidate-signals-dossier-metrics {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(0, 1fr));",
            ".candidate-signals-evidence-structure-stats {",
            ".candidate-signals-scrutiny-matrix {",
            ".candidate-signals-poll-gauge-track {",
            ".candidate-signals-poll-gauge-kicker {",
            ".candidate-signals-scope-count {",
            ".candidate-signals-scope-percentage {",
            "grid-template-rows: auto auto minmax(64px, 1fr);",
            "align-content: space-between;",
            "min-height: 64px;",
            "font-size: 22px;",
            "min-height: 120px;",
            ".candidate-signals-composition-stack {",
            ".candidate-signals-dossier-name {",
            "font-size: 23px;",
            ".candidate-signals-dossier-metric.is-composite",
            "font-size: 18px;",
            "min-height: 72px;",
            ".candidate-signals-dossier-composition-stack {",
            "height: 10px;",
            ".candidate-signals-dossier-visibility-summary",
            ".candidate-signals-summary-meta-label {",
            ".candidate-signals-summary-meta-value {",
            ".candidate-signals-dossier-scrutiny-block.is-archive.has-signal {",
            "font-size: 22px;",
            "font-size: 11px;",
            "min-height: 148px;",
            ".candidate-signals-poll-facts {",
            ".candidate-signals-poll-fact-label {",
            ".candidate-signals-poll-fact-value {",
            '"label label"',
            '"count percentage";',
            "font-weight: 620;",
            ".candidate-signals-analysis-card:nth-child(even) {",
            ".candidate-signals-latest-development {",
            "font-size: 13px;",
            "font-size: 10.5px;",
            "font-family:",
        ):
            self.assertIn(required, self.css)

    def test_stage5_compact_scrollable_workspace_height(self):
        desktop_start = self.css.index("@media (min-width: 1180px)")
        tablet_start = self.css.index(
            "@media (min-width: 760px) and (max-width: 1179px)"
        )
        desktop = self.css[desktop_start:tablet_start]

        for required in (
            "height: 430px;",
            "max-height: 430px;",
            "height: 100%;",
            "position: relative;",
            "overflow-y: auto;",
            "overscroll-behavior: contain;",
            "scrollbar-width: thin;",
        ):
            self.assertIn(required, desktop)

        self.assertIn(".candidate-signals-analysis-body,", desktop)
        self.assertIn(".candidate-signals-dossier-body {", desktop)
        self.assertNotIn("position: sticky;", desktop)
        self.assertNotIn("max-height: min(860px", desktop)

    def test_fetch_is_not_connected_to_tab_activation(self):
        interaction = self.hybrid_js[
            self.hybrid_js.index("  function bindInteractions()") :
            self.hybrid_js.index("  function renderTopMediaPulsePanel(")
        ]
        active_view = self.hybrid_js[
            self.hybrid_js.index("  function setActiveSignalView(") :
            self.hybrid_js.index("  function revealActiveTab(")
        ]
        self.assertNotIn("candidate_signals.json", interaction + active_view)
        self.assertNotIn(".load(", interaction + active_view)

    def test_changed_scope_excludes_generated_json_and_portraits(self):
        completed = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=ROOT,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        changed = {
            line[3:]
            for line in completed.stdout.splitlines()
            if len(line) > 3
        }
        self.assertEqual(
            changed,
            {
                "assets/candidate-signals-workspace.js",
                "assets/candidate-signals.css",
                "assets/hybrid-dashboard.js",
                "index.html",
                "test_candidate_signals_frontend.py",
                "test_candidate_signals_workspace.py",
            },
        )
        self.assertFalse(any(path.endswith(".json") for path in changed))
        self.assertFalse(any(path.startswith("assets/candidates/") for path in changed))

    def test_all_css_rule_selectors_are_candidate_signals_scoped(self):
        without_comments = re.sub(r"/\*.*?\*/", "", self.css, flags=re.DOTALL)
        selectors = re.findall(r"(?:^|\})([^{}]+)\{", without_comments)
        checked = 0
        for selector_group in selectors:
            selector_group = selector_group.strip()
            if not selector_group or selector_group.startswith("@"):
                continue
            for selector in selector_group.split(","):
                selector = selector.strip()
                self.assertTrue(
                    selector.startswith(".candidate-signals-"),
                    f"unscoped selector: {selector}",
                )
                checked += 1
        self.assertGreater(checked, 30)
        self.assertNotIn(":root", self.css)




def test_filtered_candidate_hidden_state_has_explicit_css_contract():
    import re
    from pathlib import Path

    css = (
        Path(__file__).resolve().parent
        / "assets"
        / "candidate-signals.css"
    ).read_text(encoding="utf-8")

    rule = re.search(
        r"\.candidate-signals-candidate-button\[hidden\]\s*,"
        r"\s*\.candidate-signals-monitor-empty\[hidden\]\s*"
        r"\{(?P<body>[^}]*)\}",
        css,
        re.DOTALL,
    )

    assert rule is not None
    assert re.search(
        r"\bdisplay\s*:\s*none\s*;",
        rule.group("body"),
    )

if __name__ == "__main__":
    unittest.main()
