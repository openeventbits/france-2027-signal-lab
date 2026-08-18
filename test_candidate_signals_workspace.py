from pathlib import Path
from datetime import date, timedelta
import json
import re
import subprocess
import unittest

from test_candidate_signals_frontend import dynamic_schema_12_payload


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


def candidate_attention_state(rows):
    start = date(2026, 7, 7)

    candidates = []

    flags = [
        "event_amplified",
        "sustained_decline",
        "stable",
    ]

    for candidate_index, row in enumerate(rows):
        daily_series = []

        for offset in range(31):
            current = start + timedelta(days=offset)

            # Deliberately make the first observation the full-period peak.
            # Because the UI is a 30-day view, this point MUST be excluded.
            if offset == 0:
                views = 99999 + candidate_index
            elif offset == 8:
                views = 3333 + candidate_index
            else:
                views = 500 + candidate_index * 10 + offset

            daily_series.append(
                {
                    "date": current.isoformat(),
                    "views": views,
                }
            )

        candidates.append(
            {
                "candidate_id": row["candidate_id"],
                "candidate_name": row["candidate_name"],
                "canonical_article": row["candidate_name"],
                "article_url": (
                    "https://fr.wikipedia.org/wiki/"
                    + row["candidate_id"]
                ),
                "latest_7_views": 7000 + candidate_index,
                "previous_7_views": 8000 + candidate_index,
                "change_7_pct": (
                    12.5 if candidate_index == 0 else -11.9
                ),
                "latest_28_views": 23000 + candidate_index,
                "previous_28_views": 26000 + candidate_index,
                "change_28_pct": -11.5 - candidate_index,
                "latest_7_peak_date": "2026-08-05",
                "latest_7_peak_views": 900,
                "latest_7_peak_share": 0.12,
                "change_7_peak_removed_pct": (
                    1.3 if candidate_index == 0 else -7.2
                ),
                "period_peak_date": "2026-07-07",
                "period_peak_views": 99999 + candidate_index,
                "interpretation_flag": flags[
                    min(candidate_index, len(flags) - 1)
                ],
                "daily_series": daily_series,
            }
        )

    payload = {
        "schema_version": "1.0",
        "period": {
            "start_date": "2026-07-07",
            "end_date": "2026-08-06",
            "days": 31,
            "data_as_of": "2026-08-06",
        },
        "methodology": {
            "label": "Wikipedia Attention",
            "interpretation": (
                "French Wikipedia pageviews measure "
                "article-reading attention."
            ),
            "not_measures": [
                "unique individuals",
                "sentiment",
                "approval",
                "electoral support",
                "voting intention",
            ],
        },
        "candidates": candidates,
    }

    return {
        "status": "ready",
        "payload": payload,
        "reason": None,
    }




def candidate_visibility_history_state(
    rows,
    campaign_zero=False,
    general_gap_index=10,
):
    start = date(2026, 7, 19)
    day_values = [
        (
            start
            + timedelta(days=offset)
        ).isoformat()
        for offset in range(29)
    ]

    campaign_denominators = [
        {
            "date": current_date,
            "record_count": 4,
            "publisher_count": 3,
        }
        for current_date in day_values
    ]

    general_denominators = [
        {
            "date": current_date,
            "record_count": (
                0
                if index == general_gap_index
                else 3
            ),
            "publisher_count": (
                0
                if index == general_gap_index
                else 3
            ),
        }
        for index, current_date
        in enumerate(day_values)
    ]

    candidates = []

    for candidate_index, row in enumerate(rows):
        campaign_count = (
            0
            if campaign_zero
            else candidate_index + 1
        )

        campaign_series = []
        general_series = []

        for day_index, current_date in enumerate(
            day_values
        ):
            campaign_series.append(
                {
                    "date": current_date,
                    "record_count": campaign_count,
                    "share": round(
                        campaign_count / 4,
                        3,
                    ),
                    "publisher_count": min(
                        campaign_count,
                        2,
                    ),
                }
            )

            if day_index == general_gap_index:
                general_series.append(
                    {
                        "date": current_date,
                        "record_count": 0,
                        "share": None,
                        "publisher_count": 0,
                    }
                )
            else:
                general_count = min(
                    candidate_index + 1,
                    3,
                )

                general_series.append(
                    {
                        "date": current_date,
                        "record_count": general_count,
                        "share": round(
                            general_count / 3,
                            3,
                        ),
                        "publisher_count": min(
                            general_count,
                            2,
                        ),
                    }
                )

        candidates.append(
            {
                "candidate_id": row["candidate_id"],
                "candidate_name": row["candidate_name"],
                "campaign_attention": {
                    "daily_series": campaign_series,
                },
                "general_visibility": {
                    "daily_series": general_series,
                },
            }
        )

    return {
        "status": "ready",
        "reason": None,
        "payload": {
            "schema_version": "1.0",
            "period": {
                "start_date": day_values[0],
                "end_date": day_values[-1],
                "days": 29,
                "data_as_of": day_values[-1],
                "day_boundary": "UTC",
                "current_utc_day_excluded": True,
            },
            "lanes": {
                "campaign_attention": {
                    "daily_denominators":
                        campaign_denominators,
                },
                "general_visibility": {
                    "daily_denominators":
                        general_denominators,
                },
            },
            "candidates": candidates,
        },
    }

def run_workspace(
    input_payload,
    selected_id=None,
    action=None,
    candidate_attention=None,
    candidate_visibility_history=None,
):
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
    if (name === "class") this.className = String(value);
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
  createElement(tagName) { return new MiniNode(tagName); },
  createElementNS(_namespace, tagName) {
    return new MiniNode(tagName);
  }
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
    candidateAttention: input.candidateAttention,
    candidateVisibilityHistory:
      input.candidateVisibilityHistory,
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
if (input.action === "main-only") {
  mount.querySelector(".candidate-signals-filter-button").dispatch("click");
}
if (input.action && input.action.type === "search") {
  const search = mount.querySelector(".candidate-signals-search-input");
  search.value = input.action.term;
  search.dispatch("input");
}

function details() {
  const buttons = mount.querySelectorAll(".candidate-signals-candidate-button");
  const links = mount.querySelectorAll(".candidate-signals-source-link");
  const workspace = mount.querySelector(".candidate-signals-workspace");
  const analysisBody =
    mount.querySelector(".candidate-signals-analysis-body");
  const monitorFactLabels = buttons.flatMap(
    button =>
      button
        .querySelectorAll(".candidate-signals-candidate-fact-label")
        .map(node => node.textContent)
  );
  const scrutinyColumns =
    mount.querySelectorAll(".candidate-signals-scrutiny-column");
  const dossierScrutinyLabels =
    mount.querySelectorAll(".candidate-signals-dossier-scrutiny-label");
  const latestDevelopmentHeadings = [
    mount
      .querySelector(".candidate-signals-latest-development")
      ?.querySelector(".candidate-signals-subsection-title") || null,
    mount
      .querySelector(".candidate-signals-dossier-development")
      ?.querySelector(".candidate-signals-dossier-card-title") || null
  ].filter(Boolean);
  const wikipediaHeading =
    mount
      .querySelectorAll(".candidate-signals-subsection-title")
      .find(
        node =>
          node.textContent ===
          "WIKIPEDIA ATTENTION · 30 DAYS"
      ) || null;
  const wikipediaPoints =
    mount.querySelectorAll(".candidate-signals-wikipedia-point");
  const wikipediaLines =
    mount.querySelectorAll(".candidate-signals-wikipedia-line");
  const wikipediaPeakPoints =
    wikipediaPoints.filter(
      node => node.className.split(/\s+/).includes("is-peak")
    );
  const wikipediaLatestPoints =
    wikipediaPoints.filter(
      node => node.className.split(/\s+/).includes("is-latest")
    );
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
    visibleCandidateOrder: buttons
      .filter(button => !button.hidden)
      .map(button => button.dataset.candidateSignalsCandidate),
    filterPressed:
      mount.querySelector(".candidate-signals-filter-button")
        ?.getAttribute("aria-pressed") || null,
    noMatchesHidden:
      mount.querySelector(".candidate-signals-monitor-empty")?.hidden ?? null,
    pressed: buttons.map(button => button.getAttribute("aria-pressed")),
    primaryOrder: workspace
      ? workspace.children.map(node => node.className)
      : [],
    regionTitles: mount.querySelectorAll(".candidate-signals-region-title")
      .map(node => node.textContent),
    analysisCardTitles:
      mount.querySelectorAll(".candidate-signals-analysis-card-title")
        .map(node => node.textContent),
    analysisBodyOrder:
      analysisBody
        ? analysisBody.children.map(node => node.className)
        : [],
    wikipediaPanelCount:
      mount.querySelectorAll(
        ".candidate-signals-wikipedia-attention"
      ).length,
    wikipediaPointTitles:
      wikipediaPoints.map(node => {
        const title = node.querySelector("title");
        return title ? title.textContent : null;
      }),
    wikipediaLineCount:
      wikipediaLines.length,
    wikipediaPeakMarkerCount:
      wikipediaPeakPoints.length,
    wikipediaLatestMarkerCount:
      wikipediaLatestPoints.length,
    wikipediaHeadingTooltip:
      wikipediaHeading
        ? wikipediaHeading.getAttribute("title") || null
        : null,
    dossierCardTitles:
      mount.querySelectorAll(".candidate-signals-dossier-card-title")
        .map(node => node.textContent),
    monitorButtonTexts:
      buttons.map(button => button.textContent),
    monitorFactLabels,
    scrutinyColumnDetails:
      scrutinyColumns.map(node => ({
        text: node.textContent,
        title: node.getAttribute("title") || null,
        ariaLabel: node.getAttribute("aria-label") || null
      })),
    dossierScrutinyLabelDetails:
      dossierScrutinyLabels.map(node => ({
        text: node.textContent,
        title: node.getAttribute("title") || null,
        ariaLabel: node.getAttribute("aria-label") || null
      })),
    latestDevelopmentHeadingDetails:
      latestDevelopmentHeadings.map(node => ({
        text: node.textContent,
        title: node.getAttribute("title") || null,
        ariaLabel: node.getAttribute("aria-label") || null
      })),
    monitorEvidenceCounts:
      buttons.map(
        button =>
          button.querySelectorAll(
            ".candidate-signals-candidate-evidence"
          ).length
      ),
    analysisCardTexts:
      mount.querySelectorAll(".candidate-signals-analysis-card")
        .map(node => node.textContent),
    attentionRowTexts:
      mount.querySelectorAll(".candidate-signals-attention-row")
        .map(node => node.textContent),
    attentionTrackCount:
      mount.querySelectorAll(".candidate-signals-attention-track").length,
    historyChartCount:
      mount.querySelectorAll(
        ".candidate-signals-history-mini"
      ).length,
    historyLineCount:
      mount.querySelectorAll(
        ".candidate-signals-history-line"
      ).length,
    historyLineClasses:
      mount.querySelectorAll(
        ".candidate-signals-history-line"
      ).map(node => node.className),
    historyLinePoints:
      mount.querySelectorAll(
        ".candidate-signals-history-line"
      ).map(node => node.getAttribute("points")),
    historyPointCount:
      mount.querySelectorAll(
        ".candidate-signals-history-point"
      ).length,
    historyPointTitles:
      mount.querySelectorAll(
        ".candidate-signals-history-point"
      ).map(node => {
        const title = node.querySelector("title");
        return title ? title.textContent : null;
      }),
    historySvgAria:
      mount.querySelectorAll(
        ".candidate-signals-history-chart"
      ).map(
        node => node.getAttribute("aria-label")
      ),
    historyMetaTexts:
      mount.querySelectorAll(
        ".candidate-signals-history-meta"
      ).map(node => node.textContent),
    historyStateTexts:
      mount.querySelectorAll(
        ".candidate-signals-history-state"
      ).map(node => node.textContent),
    scrutinyCellCount:
      mount.querySelectorAll(".candidate-signals-scrutiny-cell").length,
    dossierMetricTexts:
      mount.querySelectorAll(".candidate-signals-dossier-metric")
        .map(node => node.textContent),
    dossierCardTexts:
      mount.querySelectorAll(".candidate-signals-dossier-card")
        .map(node => node.textContent),
    evidenceGroupTexts:
      mount.querySelectorAll(".candidate-signals-evidence-group")
        .map(node => node.textContent),
    cardStateTexts:
      mount.querySelectorAll(".candidate-signals-card-state")
        .map(node => node.textContent),
    dossierScopeCellCount:
      mount.querySelectorAll(".candidate-signals-dossier-scope-cell").length,
    dossierStructureStatCount:
      mount.querySelectorAll(".candidate-signals-structure-stat").length,
    dossierStructureRatioCount:
      mount.querySelectorAll(
        ".candidate-signals-dossier-structure-ratio"
      ).length,
    dossierScrutinyMetricCount:
      mount.querySelectorAll(
        ".candidate-signals-dossier-scrutiny-metric"
      ).length,
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
                "candidateAttention": candidate_attention,
                "candidateVisibilityHistory":
                    candidate_visibility_history,
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


    def test_visibility_history_renders_two_independent_daily_share_charts(self):
        history = candidate_visibility_history_state(
            self.rows
        )

        result = run_workspace(
            payload(self.rows),
            candidate_visibility_history=history,
        )

        self.assertEqual(
            result["historyChartCount"],
            2,
        )

        # Campaign: one continuous segment.
        # General: one denominator-zero gap => two segments.
        self.assertEqual(
            result["historyLineCount"],
            3,
        )

        primary_lines = [
            value
            for value in result[
                "historyLineClasses"
            ]
            if "is-primary" in value
        ]

        general_lines = [
            value
            for value in result[
                "historyLineClasses"
            ]
            if "is-general" in value
        ]

        self.assertEqual(
            len(primary_lines),
            1,
        )

        self.assertEqual(
            len(general_lines),
            2,
        )

        self.assertEqual(
            result["historyPointCount"],
            57,
        )

        self.assertEqual(
            len(result["historyMetaTexts"]),
            2,
        )

        for meta in result["historyMetaTexts"]:
            self.assertIn(
                "29D DAILY SHARE",
                meta,
            )
            self.assertIn(
                "THROUGH 16 AUG 2026",
                meta,
            )

        self.assertEqual(
            len(result["historySvgAria"]),
            2,
        )

        for label in result["historySvgAria"]:
            self.assertIn(
                "daily share of lane coverage",
                label,
            )
            self.assertIn(
                "Gaps mark days with no lane denominator.",
                label,
            )

        titles = [
            value
            for value in result[
                "historyPointTitles"
            ]
            if value
        ]

        self.assertTrue(titles)

        for required in (
            "daily share",
            "candidate ",
            "publisher",
            "lane denominator",
        ):
            self.assertTrue(
                all(
                    required in value
                    for value in titles
                )
            )

    def test_all_zero_daily_share_remains_visible_on_baseline(self):
        history = candidate_visibility_history_state(
            self.rows,
            campaign_zero=True,
        )

        result = run_workspace(
            payload(self.rows),
            candidate_visibility_history=history,
        )

        primary = [
            points
            for class_name, points in zip(
                result["historyLineClasses"],
                result["historyLinePoints"],
            )
            if "is-primary" in class_name
        ]

        self.assertEqual(
            len(primary),
            1,
        )

        coordinates = primary[0].split()

        self.assertEqual(
            len(coordinates),
            29,
        )

        y_values = {
            coordinate.split(",")[1]
            for coordinate in coordinates
        }

        self.assertEqual(
            len(y_values),
            1,
        )

    def test_history_unavailable_does_not_remove_snapshot_metrics(self):
        history = {
            "status": "unavailable",
            "payload": None,
            "reason": "fetch_failed",
        }

        result = run_workspace(
            payload(self.rows),
            candidate_visibility_history=history,
        )

        self.assertEqual(
            result["attentionTrackCount"],
            2,
        )

        self.assertEqual(
            result["historyChartCount"],
            2,
        )

        self.assertEqual(
            result["historyLineCount"],
            0,
        )

        self.assertEqual(
            result["historyStateTexts"],
            [
                "29-day daily-share history unavailable.",
                "29-day daily-share history unavailable.",
            ],
        )

        self.assertTrue(
            any(
                "Campaign / election"
                in value
                for value in result[
                    "attentionRowTexts"
                ]
            )
        )

        self.assertTrue(
            any(
                "General visibility"
                in value
                for value in result[
                    "attentionRowTexts"
                ]
            )
        )

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

    def test_monitor_orders_point_scores_then_range_only_then_not_tested(self):
        def row(identifier, score=None, state="reported"):
            value = json.loads(json.dumps(self.rows[0]))
            value["candidate_id"] = identifier
            value["candidate_name"] = identifier.replace("-", " ").title()
            polling = value["polling"]

            if state == "reported":
                polling.update(
                    {
                        "evidence_state": "reported",
                        "hypothesis_count": 1,
                        "range_min": score if score is not None else 4.0,
                        "range_max": score if score is not None else 6.0,
                        "selected_hypothesis_score": score,
                        "selected_hypothesis_rank": (
                            1 if score is not None else None
                        ),
                    }
                )
            else:
                polling.update(
                    {
                        "evidence_state": "not_tested",
                        "hypothesis_count": None,
                        "range_min": None,
                        "range_max": None,
                        "selected_hypothesis_score": None,
                        "selected_hypothesis_rank": None,
                    }
                )

            return value

        rows = [
            row("low-score", 5),
            row("equal-a", 10),
            row("range-only"),
            row("equal-b", 10),
            row("not-tested", state="not_tested"),
        ]

        result = run_workspace(payload(rows))
        expected = [
            "equal-a",
            "equal-b",
            "low-score",
            "range-only",
            "not-tested",
        ]

        self.assertEqual(result["candidateOrder"], expected)
        self.assertEqual(result["resolved"], "equal-a")
        self.assertEqual(
            result["pressed"],
            ["true", "false", "false", "false", "false"],
        )
        self.assertNotIn(".sort(", self.workspace_js)
        self.assertIn(
            "function orderWorkspaceCandidates(candidates)",
            self.workspace_js,
        )

    def test_only_active_main_and_secondary_candidates_are_rendered(self):
        published = json.loads(
            CANDIDATE_JSON.read_text(encoding="utf-8")
        )
        result = run_workspace(published)

        active_ids = {
            *published["active_monitoring_field"]["main"],
            *published["active_monitoring_field"]["secondary"],
        }
        source_active = [
            candidate
            for candidate in published["candidates"]
            if candidate["candidate_id"] in active_ids
        ]
        by_id = {
            candidate["candidate_id"]: candidate
            for candidate in source_active
        }

        self.assertEqual(
            len(result["candidateOrder"]),
            published["active_monitoring_field"]["counts"]["active"],
        )
        self.assertEqual(set(result["candidateOrder"]), active_ids)

        groups = []
        point_scores = []
        range_only = []
        not_tested = []

        for identifier in result["candidateOrder"]:
            polling = by_id[identifier]["polling"]
            score = polling["selected_hypothesis_score"]

            if (
                polling["evidence_state"] == "reported"
                and isinstance(score, (int, float))
            ):
                groups.append(0)
                point_scores.append(float(score))
            elif polling["evidence_state"] == "reported":
                groups.append(1)
                range_only.append(identifier)
            else:
                groups.append(2)
                not_tested.append(identifier)

        source_range_only = [
            candidate["candidate_id"]
            for candidate in source_active
            if (
                candidate["polling"]["evidence_state"] == "reported"
                and candidate["polling"]["selected_hypothesis_score"]
                is None
            )
        ]
        source_not_tested = [
            candidate["candidate_id"]
            for candidate in source_active
            if candidate["polling"]["evidence_state"] != "reported"
        ]

        self.assertEqual(groups, sorted(groups))
        self.assertEqual(
            point_scores,
            sorted(point_scores, reverse=True),
        )
        self.assertEqual(range_only, source_range_only)
        self.assertEqual(not_tested, source_not_tested)
        self.assertEqual(
            result["resolved"],
            result["candidateOrder"][0],
        )

    def test_dynamic_active_workspace_search_and_main_only_filter(self):
        published = dynamic_schema_12_payload()
        initial = run_workspace(published)
        self.assertEqual(initial["status"], "ready")
        self.assertEqual(
            set(initial["candidateOrder"]),
            {
                "dynamic-candidate-01",
                "dynamic-candidate-02",
                "dynamic-candidate-03",
            },
        )
        self.assertEqual(
            initial["visibleCandidateOrder"],
            initial["candidateOrder"],
        )
        self.assertNotIn("dynamic-candidate-04", initial["candidateOrder"])

        main_only = run_workspace(
            published,
            selected_id="dynamic-candidate-03",
            action="main-only",
        )
        self.assertEqual(main_only["filterPressed"], "true")
        self.assertEqual(
            set(main_only["visibleCandidateOrder"]),
            {"dynamic-candidate-01", "dynamic-candidate-02"},
        )
        self.assertNotIn(
            "dynamic-candidate-03",
            main_only["visibleCandidateOrder"],
        )

        hidden_search = run_workspace(
            published,
            action={"type": "search", "term": "Dynamic Candidate 04"},
        )
        self.assertEqual(hidden_search["visibleCandidateOrder"], [])
        self.assertFalse(hidden_search["noMatchesHidden"])

    def test_dynamic_tier_reassignment_changes_filter_membership(self):
        baseline = dynamic_schema_12_payload(
            ("main", "secondary", "hidden", "hidden")
        )
        promoted = dynamic_schema_12_payload(
            ("main", "main", "hidden", "hidden")
        )
        demoted = dynamic_schema_12_payload(
            ("hidden", "secondary", "main", "hidden")
        )

        baseline_main = run_workspace(baseline, action="main-only")
        promoted_main = run_workspace(promoted, action="main-only")
        demoted_all = run_workspace(demoted)
        demoted_main = run_workspace(demoted, action="main-only")

        self.assertEqual(
            baseline_main["visibleCandidateOrder"],
            ["dynamic-candidate-01"],
        )
        self.assertEqual(
            set(promoted_main["visibleCandidateOrder"]),
            {"dynamic-candidate-01", "dynamic-candidate-02"},
        )
        self.assertNotIn(
            "dynamic-candidate-01",
            demoted_all["candidateOrder"],
        )
        self.assertEqual(
            demoted_main["visibleCandidateOrder"],
            ["dynamic-candidate-03"],
        )

    def test_all_hidden_dynamic_field_renders_no_monitor_candidates(self):
        result = run_workspace(dynamic_schema_12_payload(("hidden",)))
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["candidateOrder"], [])
        self.assertEqual(result["visibleCandidateOrder"], [])

    def test_valid_active_selection_is_preserved_and_hidden_falls_back(self):
        published = json.loads(
            CANDIDATE_JSON.read_text(encoding="utf-8")
        )
        active_set = {
            *published["active_monitoring_field"]["main"],
            *published["active_monitoring_field"]["secondary"],
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
        self.assertEqual(
            len(preserved["pressed"]),
            published["active_monitoring_field"]["counts"]["active"],
        )
        self.assertEqual(
            hidden["resolved"],
            hidden["candidateOrder"][0],
        )
        self.assertEqual(
            invalid["resolved"],
            invalid["candidateOrder"][0],
        )
        self.assertEqual(
            hidden["candidateOrder"],
            invalid["candidateOrder"],
        )

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

    def test_not_tested_polling_uses_poll_specific_copy(self):
        source = payload(self.rows)
        selected_id = source["candidates"][0]["candidate_id"]
        source["candidates"][0]["polling"].update(
            {
                "evidence_state": "not_tested",
                "hypothesis_count": None,
                "range_min": None,
                "range_max": None,
                "selected_hypothesis_score": None,
                "selected_hypothesis_rank": None,
            }
        )

        result = run_workspace(source, selected_id)
        text = result["text"]

        self.assertEqual(result["resolved"], selected_id)
        self.assertIn("POLL EVIDENCENot tested", text)
        self.assertIn("Point estimateNot tested", text)
        self.assertIn("Published rangeNot tested", text)
        self.assertIn("Not tested in featured package", text)
        self.assertIn(
            "No accepted first-round test in the current polling window.",
            text,
        )
        self.assertNotIn("Point estimateNot published", text)
        self.assertNotIn("Published rangeNot published", text)
        self.assertIn(
            'const NOT_TESTED = "Not tested";',
            self.workspace_js,
        )
        self.assertIn(
            'pollText === MISSING || pollText === NOT_TESTED',
            self.workspace_js,
        )

    def test_absent_general_visibility_is_not_zero_or_not_published(self):
        source = payload(self.rows)
        selected_id = source["candidates"][0]["candidate_id"]
        source["candidates"][0]["general_visibility"] = None

        result = run_workspace(source, selected_id)

        self.assertEqual(result["resolved"], selected_id)
        self.assertIn("Point estimate0%", result["text"])
        self.assertIn(
            "Campaign / election0 records · 0%",
            result["text"],
        )
        self.assertIn(
            "No current general visibility evidence.",
            result["analysisCardTexts"][1],
        )
        self.assertEqual(result["attentionTrackCount"], 1)

        visibility = result["dossierCardTexts"][0]
        self.assertIn("Campaign / election0 records · 0%", visibility)
        self.assertNotIn("General visibilityNot published", visibility)

        general_group = next(
            text
            for text in result["evidenceGroupTexts"]
            if text.startswith("GENERAL STRUCTURE")
        )
        self.assertEqual(
            general_group,
            "GENERAL STRUCTURENo current general visibility evidence.",
        )

        range_only = payload(self.rows)
        range_selected_id = range_only["candidates"][0]["candidate_id"]
        range_only["candidates"][0]["polling"][
            "selected_hypothesis_score"
        ] = None
        range_only["candidates"][0]["polling"][
            "selected_hypothesis_rank"
        ] = None

        range_result = run_workspace(
            range_only,
            range_selected_id,
        )

        self.assertEqual(
            range_result["resolved"],
            range_selected_id,
        )
        self.assertIn(
            "Point estimateRange only",
            range_result["text"],
        )

    def test_absent_campaign_keeps_real_general_visibility_only(self):
        source = payload(self.rows)
        selected_id = source["candidates"][0]["candidate_id"]
        source["candidates"][0]["campaign_attention"] = None

        result = run_workspace(source, selected_id)

        attention = result["analysisCardTexts"][1]
        self.assertIn(
            "No current campaign/election evidence.",
            attention,
        )
        self.assertIn("General visibility25%", attention)
        self.assertEqual(result["attentionTrackCount"], 1)

        coverage = result["analysisCardTexts"][2]
        self.assertIn(
            "No campaign/election evidence observed in the current period.",
            coverage,
        )

        visibility = result["dossierCardTexts"][0]
        self.assertIn("General visibility1 record · 25%", visibility)
        self.assertNotIn("Campaign / electionNot published", visibility)
        self.assertEqual(result["dossierScopeCellCount"], 0)

        structure = result["dossierCardTexts"][1]
        self.assertIn(
            "No campaign/election evidence observed in the current period.",
            structure,
        )
        self.assertEqual(result["dossierStructureStatCount"], 0)
        self.assertEqual(result["dossierStructureRatioCount"], 0)

        self.assertEqual(len(result["dossierMetricTexts"]), 3)
        self.assertTrue(
            any(
                "CAMPAIGN / ELECTION EVIDENCE"
                "No current campaign/election evidence."
                in text
                for text in result["dossierMetricTexts"]
            )
        )
        self.assertFalse(
            any(
                text.startswith("ACTIVE DAYS")
                for text in result["dossierMetricTexts"]
            )
        )

    def test_both_visibility_dimensions_collapse_to_one_state(self):
        source = payload(self.rows)
        selected_id = source["candidates"][0]["candidate_id"]
        source["candidates"][0]["campaign_attention"] = None
        source["candidates"][0]["general_visibility"] = None

        result = run_workspace(source, selected_id)

        expected = (
            "No current campaign/election or general visibility evidence."
        )

        self.assertIn(expected, result["analysisCardTexts"][1])
        self.assertEqual(result["attentionTrackCount"], 0)

        self.assertIn(expected, result["dossierCardTexts"][0])
        self.assertEqual(result["dossierScopeCellCount"], 0)

        self.assertIn(
            "No campaign/election evidence observed in the current period.",
            result["analysisCardTexts"][2],
        )
        self.assertIn(
            "No campaign/election evidence observed in the current period.",
            result["dossierCardTexts"][1],
        )

        campaign_group = next(
            text
            for text in result["evidenceGroupTexts"]
            if text.startswith("CAMPAIGN / ELECTION STRUCTURE")
        )
        general_group = next(
            text
            for text in result["evidenceGroupTexts"]
            if text.startswith("GENERAL STRUCTURE")
        )

        self.assertEqual(
            campaign_group,
            "CAMPAIGN / ELECTION STRUCTURE"
            "No current campaign/election evidence.",
        )
        self.assertEqual(
            general_group,
            "GENERAL STRUCTURE"
            "No current general visibility evidence.",
        )

    def test_unreported_campaign_object_does_not_leak_stale_counts(self):
        source = payload(self.rows)
        selected_id = source["candidates"][0]["candidate_id"]
        campaign = source["candidates"][0]["campaign_attention"]

        # Keep deliberately stale populated fields behind a non-reported state.
        campaign["evidence_state"] = "not_reported"
        campaign["record_count"] = 99
        campaign["share"] = 0.99
        campaign["scope_counts"] = {
            "campaign": 40,
            "election": 30,
            "general": 29,
        }

        result = run_workspace(source, selected_id)

        self.assertIn(
            "No current campaign/election evidence.",
            result["analysisCardTexts"][1],
        )
        self.assertNotIn("99 REC", result["analysisCardTexts"][1])

        self.assertIn(
            "No campaign/election evidence observed in the current period.",
            result["analysisCardTexts"][2],
        )

        self.assertEqual(result["dossierScopeCellCount"], 0)
        self.assertEqual(result["dossierStructureStatCount"], 0)
        self.assertEqual(result["dossierStructureRatioCount"], 0)

        selected_monitor = next(
            text
            for text in result["monitorButtonTexts"]
            if "Zeta Candidate" in text
        )
        self.assertNotIn("Campaign / election 99", selected_monitor)
        self.assertNotIn("Attention99%", selected_monitor)

    def test_candidate_monitor_uses_semantically_specific_evidence_labels(self):
        result = run_workspace(payload(self.rows))
        labels = result["monitorFactLabels"]

        self.assertIn("CAMPAIGN ATTENTION", labels)
        self.assertIn("RACE RECORDS", labels)
        self.assertNotIn("Attention", labels)
        self.assertNotIn("Records", labels)

    def test_scrutiny_compact_labels_expose_semantic_metadata(self):
        result = run_workspace(payload(self.rows))
        expected = {
            "ABOUT": (
                "ABOUT — candidate mentioned in a claim attributed to "
                "someone else."
            ),
            "BY": "BY — candidate is the recorded claimant.",
        }

        analysis = {
            item["text"]: item
            for item in result["scrutinyColumnDetails"]
            if item["text"] in expected
        }
        self.assertEqual(set(analysis), set(expected))
        for label, semantic in expected.items():
            self.assertEqual(analysis[label]["text"], label)
            self.assertEqual(analysis[label]["title"], semantic)
            self.assertEqual(analysis[label]["ariaLabel"], semantic)

        dossier = [
            item
            for item in result["dossierScrutinyLabelDetails"]
            if item["text"] in expected
        ]
        self.assertGreaterEqual(len(dossier), 2)
        self.assertEqual({item["text"] for item in dossier}, set(expected))
        for item in dossier:
            label = item["text"]
            self.assertEqual(item["title"], expected[label])
            self.assertEqual(item["ariaLabel"], expected[label])

    def test_latest_development_headings_expose_subject_linkage_semantics(self):
        result = run_workspace(payload(self.rows))
        explanation = (
            "Newest campaign/election record with this candidate matched "
            "in the headline."
        )
        headings = result["latestDevelopmentHeadingDetails"]

        self.assertEqual(len(headings), 2)
        for heading in headings:
            self.assertEqual(heading["text"], "LATEST DEVELOPMENT")
            self.assertEqual(heading["title"], explanation)
            self.assertIn("LATEST DEVELOPMENT", heading["ariaLabel"])
            self.assertIn(explanation, heading["ariaLabel"])

    def test_scrutiny_absence_and_published_zero_are_distinct(self):
        absent = payload(self.rows)
        selected_id = absent["candidates"][0]["candidate_id"]
        absent["candidates"][0]["scrutiny"] = None

        absent_result = run_workspace(absent, selected_id)

        self.assertIn(
            "No scrutiny evidence is currently published.",
            absent_result["analysisCardTexts"][3],
        )
        self.assertIn(
            "No scrutiny evidence is currently published.",
            absent_result["dossierCardTexts"][2],
        )
        self.assertEqual(absent_result["scrutinyCellCount"], 0)
        self.assertEqual(absent_result["dossierScrutinyMetricCount"], 0)
        self.assertTrue(
            any(
                "SCRUTINY · 14 DAYSNo current scrutiny evidence."
                in text
                for text in absent_result["dossierMetricTexts"]
            )
        )

        scrutiny_group = next(
            text
            for text in absent_result["evidenceGroupTexts"]
            if text.startswith("CLAIM SCRUTINY DETAIL")
        )
        self.assertEqual(
            scrutiny_group,
            "CLAIM SCRUTINY DETAIL"
            "No scrutiny evidence currently published.",
        )

        zero = payload(self.rows)
        zero_selected_id = zero["candidates"][0]["candidate_id"]

        for period in ("latest_14_days", "archive"):
            zero_period = zero["candidates"][0]["scrutiny"][period]
            zero_period["review_count"] = 0
            zero_period["by_count"] = 0
            zero_period["about_count"] = 0

        zero_result = run_workspace(zero, zero_selected_id)

        self.assertEqual(zero_result["scrutinyCellCount"], 6)
        self.assertEqual(zero_result["dossierScrutinyMetricCount"], 6)
        self.assertNotIn(
            "No scrutiny evidence is currently published.",
            zero_result["analysisCardTexts"][3],
        )
        self.assertNotIn(
            "No scrutiny evidence is currently published.",
            zero_result["dossierCardTexts"][2],
        )
        self.assertIn(
            "SCRUTINY · 14 DAYS0 about · 0 by",
            "".join(zero_result["dossierMetricTexts"]),
        )

    def test_monitor_no_data_candidate_has_no_placeholder_fact_strip(self):
        rows = json.loads(json.dumps(self.rows))
        rows[0]["campaign_attention"] = None
        rows[0]["general_visibility"] = None
        rows[0]["scrutiny"] = None

        result = run_workspace(payload(rows), "zeta")

        selected_index = result["candidateOrder"].index("zeta")
        selected_text = result["monitorButtonTexts"][selected_index]

        self.assertIn("No current coverage evidence", selected_text)
        self.assertNotIn("Not published", selected_text)
        self.assertEqual(
            result["monitorEvidenceCounts"][selected_index],
            0,
        )

        # Other populated candidates retain their fact strips.
        self.assertTrue(
            any(
                count == 1
                for index, count in enumerate(result["monitorEvidenceCounts"])
                if index != selected_index
            )
        )

    def test_populated_empty_state_redesign_preserves_existing_semantics(self):
        result = run_workspace(payload(self.rows), "zeta")

        self.assertEqual(len(result["analysisCardTexts"]), 4)
        self.assertEqual(len(result["dossierMetricTexts"]), 4)
        self.assertEqual(len(result["dossierCardTexts"]), 4)

        self.assertEqual(result["attentionTrackCount"], 2)
        self.assertEqual(result["dossierScopeCellCount"], 2)
        self.assertEqual(result["dossierStructureStatCount"], 4)
        self.assertEqual(result["dossierStructureRatioCount"], 2)
        self.assertEqual(result["scrutinyCellCount"], 6)
        self.assertEqual(result["dossierScrutinyMetricCount"], 6)
        self.assertEqual(len(result["evidenceGroupTexts"]), 4)

        self.assertIn("Point estimate0%", result["text"])
        self.assertIn("0 REC · 2 PUB · 3 DAYS", result["text"])
        self.assertIn(
            "Campaign / election0 records · 0%",
            result["text"],
        )
        self.assertIn("General visibility1 record · 25%", result["text"])
        self.assertIn("SCRUTINY · 14 DAYS", result["text"])

        self.assertFalse(
            any(
                "No current campaign/election or general visibility evidence."
                in text
                for text in result["analysisCardTexts"]
            )
        )
        self.assertFalse(
            any(
                "No scrutiny evidence is currently published."
                in text
                for text in result["dossierCardTexts"]
            )
        )

    def test_visibility_composition_and_scrutiny_dimensions_remain_separate(self):
        result = run_workspace(payload(self.rows))
        text = result["text"]
        for label in (
            "Campaign / election",
            "General visibility",
            "Campaign",
            "Election",
            "14 days · BY",
            "14 days · ABOUT",
            "Archive · BY",
            "Archive · ABOUT",
        ):
            self.assertIn(label, text)

        race_mix = result["analysisCardTexts"][2]
        self.assertIn("Campaign", race_mix)
        self.assertIn("Election", race_mix)
        self.assertNotIn("General", race_mix)

        self.assertIn(
            "General visibility",
            result["dossierCardTexts"][0],
        )
        self.assertNotIn("claim row", self.workspace_js.lower())

    def test_selected_analysis_has_exact_four_cards(self):
        result = run_workspace(payload(self.rows))

        self.assertEqual(
            result["analysisCardTitles"],
            [
                "POLL EVIDENCE",
                "CAMPAIGN ATTENTION",
                "RACE COVERAGE MIX",
                "SCRUTINY",
            ],
        )
        for required in (
            "function pollSummaryCard(candidate, metadata)",
            "function attentionSummaryCard(candidate, historyState)",
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


    def test_wikipedia_attention_is_final_selected_analysis_module(self):
        attention = candidate_attention_state(self.rows)

        result = run_workspace(
            payload(self.rows),
            candidate_attention=attention,
        )

        self.assertEqual(
            result["wikipediaPanelCount"],
            1,
        )
        self.assertEqual(
            result["analysisBodyOrder"][-1],
            "candidate-signals-wikipedia-attention",
        )
        self.assertIn(
            "WIKIPEDIA ATTENTION · 30 DAYS",
            result["text"],
        )

        self.assertIn(
            "30D PEAK",
            result["text"],
        )

        for label in (
            "LATEST 7D",
            "PREVIOUS 7D",
            "7D CHANGE",
            "PEAK DATE",
            "STATE",
            "DAILY PAGEVIEWS",
            "PEAK-REMOVED 7D",
            "28D TOTAL",
            "28D CHANGE",
        ):
            self.assertIn(label, result["text"])

        self.assertEqual(
            result["wikipediaLineCount"],
            1,
        )
        self.assertEqual(
            result["wikipediaPeakMarkerCount"],
            1,
        )
        self.assertEqual(
            result["wikipediaLatestMarkerCount"],
            1,
        )


    def test_wikipedia_attention_uses_exact_last_30_observations(self):
        attention = candidate_attention_state(self.rows)

        result = run_workspace(
            payload(self.rows),
            candidate_attention=attention,
        )

        bars = result["wikipediaPointTitles"]

        self.assertEqual(len(bars), 30)
        self.assertTrue(
            all(title for title in bars)
        )

        # The synthetic 99,999-view point is observation 31-from-last.
        # It is the full-period peak but must NOT enter the 30-day module.
        self.assertFalse(
            any("99,999" in title for title in bars)
        )
        self.assertNotIn(
            "99,999",
            result["text"],
        )

        # The true peak inside the displayed 30-day window is 3,333.
        self.assertTrue(
            any("3,333" in title for title in bars)
        )
        self.assertIn(
            "3,333",
            result["text"],
        )


    def test_wikipedia_methodology_is_hover_only_and_cta_is_absent(self):
        attention = candidate_attention_state(self.rows)

        result = run_workspace(
            payload(self.rows),
            candidate_attention=attention,
        )

        expected = (
            "French Wikipedia pageviews measure "
            "article-reading attention. "
            "They do not measure unique individuals, "
            "sentiment, approval, electoral support, "
            "voting intention."
        )

        self.assertEqual(
            result["wikipediaHeadingTooltip"],
            expected,
        )

        # title= is metadata, not visible textContent.
        self.assertNotIn(
            expected,
            result["text"],
        )

        self.assertNotIn(
            "Open Wikipedia",
            result["text"],
        )

        self.assertNotIn(
            "candidate-signals-wikipedia-footer",
            self.workspace_js,
        )
        self.assertNotIn(
            "French Wikipedia daily pageviews · "
            "article-reading attention, not electoral support",
            result["text"],
        )
        self.assertNotIn(
            "candidate-signals-wikipedia-link",
            self.workspace_js,
        )
        self.assertNotIn(
            "Open Wikipedia",
            result["text"],
        )


    def test_wikipedia_attention_tracks_selected_candidate(self):
        attention = candidate_attention_state(self.rows)

        result = run_workspace(
            payload(self.rows),
            action="click-second",
            candidate_attention=attention,
        )

        self.assertEqual(
            result["resolved"],
            "alpha",
        )
        self.assertIn(
            "7,001",
            result["text"],
        )
        self.assertIn(
            "SUSTAINED DECLINE",
            result["text"],
        )
        self.assertNotIn(
            "EVENT AMPLIFIED",
            result["text"],
        )


    def test_wikipedia_attention_loading_and_unavailable_are_bounded(self):
        loading = run_workspace(
            payload(self.rows),
            candidate_attention={
                "status": "loading",
                "payload": None,
                "reason": None,
            },
        )

        unavailable = run_workspace(
            payload(self.rows),
            candidate_attention={
                "status": "unavailable",
                "payload": None,
                "reason": "fetch_failed",
            },
        )

        self.assertIn(
            "Loading published Wikimedia attention…",
            loading["text"],
        )
        self.assertEqual(
            loading["wikipediaPointTitles"],
            [],
        )

        self.assertIn(
            "Published Wikipedia attention is unavailable "
            "for this candidate.",
            unavailable["text"],
        )
        self.assertEqual(
            unavailable["wikipediaPointTitles"],
            [],
        )


    def test_wikipedia_attention_frontend_ownership_contract(self):
        attention_js = (
            ROOT / "assets" / "candidate-attention.js"
        ).read_text(encoding="utf-8")

        index = (
            ROOT / "index.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "candidate_attention.json",
            self.workspace_js,
        )
        self.assertNotIn(
            "fetch(",
            self.workspace_js,
        )

        self.assertNotIn(
            "fetch(",
            self.hybrid_js,
        )

        self.assertEqual(
            self.hybrid_js.count(
                '.load("candidate_attention.json")'
            ),
            1,
        )

        self.assertIn(
            "window.France2027CandidateAttention",
            attention_js,
        )
        self.assertIn(
            "fetchImplementation",
            attention_js,
        )
        self.assertIn(
            "function normalize(payload)",
            attention_js,
        )

        attention_script = (
            '<script src="assets/candidate-attention.js"></script>'
        )
        dashboard_script = (
            '<script src="assets/hybrid-dashboard.js"></script>'
        )

        self.assertIn(
            attention_script,
            index,
        )
        self.assertLess(
            index.index(attention_script),
            index.index(dashboard_script),
        )

        self.assertIn(
            "candidateAttention:",
            self.hybrid_js,
        )

        self.assertIn(
            ".candidate-signals-wikipedia-primary-metrics {",
            self.css,
        )
        self.assertIn(
            ".candidate-signals-wikipedia-svg {",
            self.css,
        )
        self.assertIn(
            ".candidate-signals-wikipedia-line {",
            self.css,
        )
        self.assertNotIn(
            ".candidate-signals-wikipedia-footer",
            self.css,
        )
        self.assertNotIn(
            ".candidate-signals-wikipedia-link",
            self.css,
        )
        self.assertNotIn(
            ".candidate-signals-wikipedia-bars {",
            self.css,
        )

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
            "function attentionSummaryCard(candidate, historyState)",
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
            'const values = ["campaign", "election"].map(key => {',
            "function analysisLatestDevelopment(candidate)",
            "function dossierLatestDevelopment(candidate)",
            "function evidenceStructureBreakdown(candidate, metadata)",
            "function candidacyEvidence(candidate)",
            "candidate-signals-composition-visual",
            "const complete = values.every(value => value !== null);",
        ):
            self.assertIn(required, self.workspace_js)

        self.assertRegex(
            self.workspace_js,
            r"composition\.complete\s*&&\s*composition\.total > 0",
        )

        for required in (
            "min-height: 120px;",
            ".candidate-signals-composition-stack {",
            "height: 12px;",
            "width: 78px;",
            "width: 118px;",
            "min-height: 132px;",
        ):
            self.assertIn(required, self.css)

    def test_empty_state_visual_contract(self):
        for required in (
            ".candidate-signals-attention-row.is-unavailable\n"
            "  .candidate-signals-attention-detail {",
            ".candidate-signals-dossier-metric.is-empty {",
            ".candidate-signals-dossier-metric.is-wide {",
            ".candidate-signals-dossier-card > "
            ".candidate-signals-card-state {",
            "grid-auto-flow: column;",
            "grid-auto-columns: minmax(0, 1fr);",
            ".candidate-signals-dossier-details-content\n"
            "  .candidate-signals-evidence-group\n"
            "  > .candidate-signals-development-empty {",
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

    def test_workspace_consumes_generated_assets_without_owning_them(self):
        source = (
            ROOT
            / "assets"
            / "candidate-signals-workspace.js"
        ).read_text(encoding="utf-8")

        self.assertNotIn("candidate_signals.json", source)
        self.assertNotIn("candidate-portraits/", source)
        self.assertNotIn("fetch(", source)
        self.assertIn("resolvePortrait", source)

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
