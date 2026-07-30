from pathlib import Path
import json
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
HYBRID_JS = ROOT / "assets" / "hybrid-dashboard.js"
SHELL_CSS = ROOT / "assets" / "final-dashboard-shell.css"

VIEW_NAMES = [
    "runoff",
    "candidates",
    "events",
    "agenda",
    "claims",
    "pollCompare",
]
TAB_IDS = [
    "signal-runoff-tab",
    "signal-candidates-tab",
    "signal-events-tab",
    "signal-agenda-tab",
    "signal-claims-tab",
    "signal-poll-compare-tab",
]
PANEL_IDS = [
    "signal-runoff-panel",
    "signal-candidates-panel",
    "signal-events-panel",
    "signal-agenda-panel",
    "signal-claims-panel",
    "polling-evidence-lab",
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
const names = ["runoff", "candidates", "events", "agenda", "claims", "pollCompare"];
const panelIds = [
  "signal-runoff-panel",
  "signal-candidates-panel",
  "signal-events-panel",
  "signal-agenda-panel",
  "signal-claims-panel",
  "polling-evidence-lab"
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


class CandidateSignalsRoutingStageATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.js = HYBRID_JS.read_text(encoding="utf-8")
        cls.css = SHELL_CSS.read_text(encoding="utf-8")
        start = cls.js.index("  const views = Object.freeze({")
        end = cls.js.index("  const viewOrder", start)
        cls.views = cls.js[start:end]
        workspace_start = cls.js.index("  function renderFocusWorkspace(")
        workspace_end = cls.js.index(
            "  function setActiveSignalView(", workspace_start
        )
        cls.workspace = cls.js[workspace_start:workspace_end]

    def render_workspace(self, hash_value=""):
        return run_router_script(
            hash_value,
            """api.renderFocusWorkspace({
              runoff: { state: "empty", message: "runoff" },
              agenda: { state: "empty", message: "agenda" },
              claims: { state: "empty", message: "claims" }
            })""",
        )

    def test_exact_six_labels_and_hashes_in_locked_order(self):
        entries = re.findall(
            r"^    (\w+): \{.*?^      label: \"([^\"]+)\","
            r".*?^      hash: \"([^\"]+)\",",
            self.views,
            re.MULTILINE | re.DOTALL,
        )
        self.assertEqual(
            entries,
            list(
                zip(
                    VIEW_NAMES,
                    [
                        "RUNOFF",
                        "CANDIDATES",
                        "EVENTS",
                        "AGENDA",
                        "CLAIM SCRUTINY",
                        "POLL COMPARE",
                    ],
                    [
                        "#signal-runoff",
                        "#signal-candidates",
                        "#signal-events",
                        "#signal-agenda",
                        "#signal-claims",
                        "#signal-poll-compare",
                    ],
                )
            ),
        )

    def test_candidates_is_default_and_active_fallback(self):
        self.assertIn('const defaultView = "candidates";', self.js)
        self.assertIn(
            "activeView: hashToView.get(window.location.hash) || defaultView",
            self.js,
        )
        self.assertIn("if (!views[view]) view = defaultView;", self.js)
        workspace = self.render_workspace("")
        candidate_tab = re.search(
            r'<button class="hybrid-tab" id="signal-candidates-tab"[^>]+>',
            workspace,
        ).group(0)
        self.assertIn('aria-selected="true"', candidate_tab)
        self.assertIn('tabindex="0"', candidate_tab)

    def test_empty_unknown_and_obsolete_hashes_normalize_with_replace_state(self):
        for hash_value in ("", "#unknown", "#signal-media"):
            with self.subTest(hash_value=hash_value):
                result = run_router_script(
                    hash_value,
                    """(() => {
                      api.handleSignalHashChange();
                      return {
                        hash: windowObject.location.hash,
                        historyCalls,
                        selected: tabs.find(tab => tab.attributes["aria-selected"] === "true").dataset.hybridView
                      };
                    })()""",
                )
                self.assertEqual(result["hash"], "#signal-candidates")
                self.assertEqual(result["historyCalls"], ["#signal-candidates"])
                self.assertEqual(result["selected"], "candidates")
        self.assertIn("window.history.replaceState(", self.js)

    def test_lower_media_tab_is_absent_but_top_media_pulse_remains(self):
        workspace = self.render_workspace()
        self.assertNotIn("MEDIA PULSE", workspace)
        self.assertNotIn("#signal-media", self.views)
        for selector in (
            'class="panel top-media-pulse"',
            'id="top-media-pulse-content"',
            'id="top-media-pulse-metrics"',
            'data-top-media-tab="overview"',
            'data-top-media-tab="coverage"',
        ):
            self.assertIn(selector, self.html + self.js)
        self.assertIn("function renderMediaPanel(", self.js)
        self.assertIn("function buildMediaViewModel()", self.js)

    def test_candidates_has_real_tab_panel_and_owned_mount(self):
        workspace = self.render_workspace()
        tab = re.search(
            r'<button class="hybrid-tab" id="signal-candidates-tab"[^>]+>',
            workspace,
        ).group(0)
        panel = re.search(
            r'<section class="hybrid-panel" id="signal-candidates-panel"[^>]+>',
            workspace,
        ).group(0)
        self.assertIn('role="tab"', tab)
        self.assertIn('aria-controls="signal-candidates-panel"', tab)
        self.assertIn('role="tabpanel"', panel)
        self.assertIn('aria-labelledby="signal-candidates-tab"', panel)
        self.assertIn('id="candidate-signals-root"', workspace)

    def test_candidate_placeholder_uses_locked_copy_only(self):
        workspace = self.render_workspace()
        for copy in (
            "CANDIDATE SIGNALS",
            "Polling · campaign attention · scrutiny",
            "Separate evidence dimensions. No combined score or forecast.",
            "Candidate evidence will be rendered in the next implementation stage.",
        ):
            self.assertIn(copy, workspace)

    def test_events_has_real_tab_and_explicit_unavailable_panel(self):
        workspace = self.render_workspace()
        self.assertRegex(
            workspace,
            r'id="signal-events-tab"[^>]+role="tab"[^>]+'
            r'aria-controls="signal-events-panel"',
        )
        self.assertRegex(
            workspace,
            r'id="signal-events-panel" role="tabpanel" '
            r'aria-labelledby="signal-events-tab"[^>]* hidden',
        )
        self.assertIn("CAMPAIGN EVENTS", workspace)
        self.assertIn("Campaign Events is not yet available.", workspace)

    def test_poll_compare_is_real_tab_controlling_existing_panel(self):
        workspace = self.render_workspace()
        poll_tab = re.search(
            r'<button class="hybrid-tab" id="signal-poll-compare-tab"[^>]+>',
            workspace,
        ).group(0)
        self.assertIn('role="tab"', poll_tab)
        self.assertIn('aria-controls="polling-evidence-lab"', poll_tab)
        opening = re.search(
            r'<section class="panel polling-evidence" '
            r'id="polling-evidence-lab"[^>]+>',
            self.html,
        ).group(0)
        self.assertIn('role="tabpanel"', opening)
        self.assertIn('aria-labelledby="signal-poll-compare-tab"', opening)
        self.assertIn(" hidden", opening)

    def test_poll_compare_panel_is_not_generated_or_duplicated(self):
        workspace = self.render_workspace()
        self.assertNotIn('id="polling-evidence-lab"', workspace)
        self.assertEqual(self.html.count('id="polling-evidence-lab"'), 1)
        self.assertEqual(
            (self.html + workspace).count('id="polling-evidence-lab"'), 1
        )

    def test_no_poll_compare_scroll_shortcut_remains(self):
        combined = self.html + self.js
        self.assertNotIn("data-hybrid-poll-compare", combined)
        self.assertNotIn("bindPollCompareShortcut", combined)
        self.assertIn('view === "pollCompare"', self.js)
        self.assertIn('document.getElementById("polling-evidence-lab")', self.js)

    def test_tablist_and_all_controls_have_required_aria(self):
        workspace = self.render_workspace()
        self.assertRegex(
            workspace,
            r'<div class="hybrid-tabs" role="tablist" '
            r'aria-label="[^"]+" aria-orientation="horizontal">',
        )
        controls = re.findall(
            r'<button class="hybrid-tab"[^>]+>[^<]+</button>', workspace
        )
        self.assertEqual(len(controls), 6)
        for index, control in enumerate(controls):
            self.assertIn(f'id="{TAB_IDS[index]}"', control)
            self.assertIn('role="tab"', control)
            self.assertIn(f'aria-controls="{PANEL_IDS[index]}"', control)
            self.assertRegex(control, r'aria-selected="(?:true|false)"')
            self.assertRegex(control, r'tabindex="(?:0|-1)"')

    def test_active_state_hides_other_panels_and_roves_tabindex(self):
        result = run_router_script(
            "#signal-candidates",
            """(() => {
              api.setActiveSignalView("events");
              return {
                tabs: tabs.map(tab => ({
                  name: tab.dataset.hybridView,
                  selected: tab.attributes["aria-selected"],
                  tabIndex: tab.tabIndex
                })),
                panels: Object.fromEntries(Object.entries(panels).map(([id, panel]) => [id, panel.hidden]))
              };
            })()""",
        )
        selected = [tab for tab in result["tabs"] if tab["selected"] == "true"]
        self.assertEqual(selected, [{"name": "events", "selected": "true", "tabIndex": 0}])
        for tab in result["tabs"]:
            if tab["name"] != "events":
                self.assertEqual(tab["tabIndex"], -1)
        self.assertFalse(result["panels"]["signal-events-panel"])
        for panel_id, hidden in result["panels"].items():
            if panel_id != "signal-events-panel":
                self.assertTrue(hidden)

    def test_keyboard_navigation_wraps_and_uses_home_end_across_six_tabs(self):
        start = self.js.index("  function bindInteractions()")
        end = self.js.index(
            '    mount.querySelectorAll("[data-hybrid-agenda-topic]")', start
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
            "setActiveSignalView(next, { focusTab: true })",
        ):
            self.assertIn(contract, keyboard)
        self.assertEqual(len(VIEW_NAMES), 6)

    def test_direct_hashes_and_hashchange_activate_recognized_views(self):
        hashes = [
            "#signal-runoff",
            "#signal-candidates",
            "#signal-events",
            "#signal-agenda",
            "#signal-claims",
            "#signal-poll-compare",
        ]
        for tab_id, hash_value in zip(TAB_IDS, hashes):
            with self.subTest(hash_value=hash_value):
                workspace = self.render_workspace(hash_value)
                tab = re.search(
                    rf'<button class="hybrid-tab" id="{tab_id}"[^>]+>',
                    workspace,
                ).group(0)
                self.assertIn('aria-selected="true"', tab)
                self.assertIn('tabindex="0"', tab)

        result = run_router_script(
            "#signal-poll-compare",
            """(() => {
              api.handleSignalHashChange();
              return {
                selected: tabs.find(tab => tab.attributes["aria-selected"] === "true").dataset.hybridView,
                pollHidden: panels["polling-evidence-lab"].hidden,
                otherPanelsHidden: panelIds.slice(0, 5).every(id => panels[id].hidden),
                historyCalls
              };
            })()""",
        )
        self.assertEqual(result["selected"], "pollCompare")
        self.assertFalse(result["pollHidden"])
        self.assertTrue(result["otherPanelsHidden"])
        self.assertEqual(result["historyCalls"], [])

    def test_user_changes_use_hash_navigation_for_browser_history(self):
        start = self.js.index("  function setViewHash(")
        end = self.js.index("  function scrollWorkspaceIfNeeded(", start)
        setter = self.js[start:end]
        self.assertIn("window.location.hash = views[view].hash;", setter)
        self.assertNotIn("replaceState", setter)
        self.assertIn(
            'window.addEventListener("hashchange", handleSignalHashChange);',
            self.js,
        )

    def test_six_column_desktop_and_horizontal_narrow_overflow(self):
        self.assertIn("repeat(6, minmax(0, 1fr));", self.html)
        self.assertIn("repeat(6, minmax(0, 1fr));", self.css)
        self.assertIn("repeat(6, minmax(112px, 1fr));", self.css)
        narrow_index = self.html[self.html.index("@media (max-width: 700px)") :]
        self.assertIn("overflow-x: auto;", narrow_index)
        self.assertIn("flex: 0 0 145px;", narrow_index)
        narrow_shell = self.css[self.css.index("@media (max-width: 860px)") :]
        self.assertIn("overflow-x: auto;", narrow_shell)
        self.assertIn("function revealActiveTab(tab)", self.js)

    def test_stage_a_has_no_candidate_data_or_matrix_dossier_implementation(self):
        combined = self.html + self.js
        self.assertNotIn('fetch("candidate_signals.json")', combined)
        self.assertNotIn("fetch('candidate_signals.json')", combined)
        self.assertNotIn("candidate-signals.css", combined)
        candidate_start = self.workspace.index('id="candidate-signals-root"')
        candidate_end = self.workspace.index("      </section>", candidate_start)
        placeholder = self.workspace[candidate_start:candidate_end]
        for forbidden in (
            "matrix",
            "dossier",
            "portrait",
            "data-candidate",
            "source-link",
        ):
            self.assertNotIn(forbidden, placeholder.lower())


if __name__ == "__main__":
    unittest.main()
