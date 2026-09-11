import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"


RACE_GLANCE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const indexSource = fs.readFileSync("index.html", "utf8").replace(/\r\n/g, "\n");

class Element {
  constructor(attributes = {}, textContent = "") {
    this.attributes = new Map(Object.entries(attributes));
    this.textContent = textContent;
    this.innerHTML = "";
    this.hidden = false;
    this.dataset = {};
    this.scrollTop = 0;
    this.scrollHeight = 200;
    this.clientHeight = 100;
  }
  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }
  removeAttribute(name) {
    this.attributes.delete(name);
  }
}

const raceTitle = new Element(
  { "data-i18n": "dashboard.race_at_a_glance" },
  "RACE AT A GLANCE"
);
const scenarioLabel = new Element(
  { "data-i18n": "race_glance.scenario" },
  "SCENARIO"
);
const latestTitle = new Element(
  {
    "data-i18n-aria-label": "race_glance.loading_latest_poll",
    "aria-label": "Loading latest poll"
  }
);
const bars = new Element(
  {
    "data-i18n-aria-label": "race_glance.reported_scores_list",
    "aria-label": "Reported candidate scores for the selected scenario. Scroll to view all candidates."
  }
);
const panel = new Element();
panel.classList = { remove() {} };
const latestSub = new Element();
const sourceLink = new Element();
const meta = new Element();
const raceMore = new Element();
const fade = new Element();
const elements = new Map([
  ["#bars", bars],
  ["#race-poll-panel", panel],
  ["#latest-title", latestTitle],
  ["#latest-sub", latestSub],
  ["#race-source", sourceLink],
  ["#meta", meta],
  ["#race-more", raceMore],
  ["#race-scroll-fade", fade]
]);
const documentListeners = new Map();
const documentElement = {
  dataset: { siteRoot: "./" },
  lang: "fr"
};
const documentObject = {
  documentElement,
  baseURI: input.href,
  readyState: "loading",
  title: "",
  querySelectorAll(selector) {
    return {
      "[data-i18n]": [raceTitle, scenarioLabel],
      "[data-i18n-aria-label]": [latestTitle, bars],
      "[data-i18n-fr27-tooltip]": [],
      "[data-fr27-language]": []
    }[selector] || [];
  },
  addEventListener(type, callback) {
    const callbacks = documentListeners.get(type) || [];
    callbacks.push(callback);
    documentListeners.set(type, callbacks);
  }
};
const windowObject = {
  document: documentObject,
  location: new URL(input.href),
  console: { warn() {} },
  addEventListener() {},
  setTimeout(callback) {
    callback();
    return 1;
  }
};
const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");
const context = {
  window: windowObject,
  globalThis: windowObject,
  document: documentObject,
  URL,
  URLSearchParams,
  Intl,
  Object,
  String,
  Number,
  Boolean,
  Array,
  Math,
  Set,
  Map,
  Date,
  console,
  input,
  raceGlanceState: {
    pollPackages: [],
    selectedHypothesisByPoll: {},
    selectedPollKey: "",
    events: [],
    scaleMax: 40
  },
  candidatePortraits: {},
  candidateMonogram(name) {
    return String(name).split(/\s+/).map(part => part[0] || "").join("");
  },
  raceCandidateMarker(name) {
    return `<i aria-hidden="true">${escapeHtml(name)}</i>`;
  },
  escapeHtml,
  escapeAttribute: escapeHtml,
  formatScore(value) {
    return `${value}%`;
  },
  deriveComparableChange() {
    return {
      classification: "NO COMPARABLE PRIOR",
      retained: [],
      deltas: []
    };
  },
  deriveRacePreviousPollDifference() {
    return {
      classification: "NO_PRIOR"
    };
  },
  formatComparableChange() {
    throw new Error("No-prior Race renderer must own its localized state");
  },
  safeSourceUrl(value) {
    return String(value || "");
  },
  requestAnimationFrame(callback) {
    callback();
  },
  $(selector) {
    return elements.get(selector) || null;
  },
  result: null
};

vm.runInNewContext(fs.readFileSync("locales/en.js", "utf8"), context);
vm.runInNewContext(fs.readFileSync("locales/fr.js", "utf8"), context);
vm.runInNewContext(fs.readFileSync("assets/localization.js", "utf8"), context);
for (const callback of documentListeners.get("DOMContentLoaded") || []) {
  callback();
}
const staticResult = {
  title: raceTitle.textContent,
  scenario: scenarioLabel.textContent,
  loadingAria: latestTitle.getAttribute("aria-label"),
  scoresAria: bars.getAttribute("aria-label")
};
context.staticResult = staticResult;
context.translate = (key, fallback, parameters) =>
  windowObject.FR27I18N.t(key, parameters, fallback);

const functionsStart = indexSource.indexOf("    function racePollDate(");
const functionsEnd = indexSource.indexOf(
  "    const pollingEvidenceFeature =",
  functionsStart
);
vm.runInNewContext(
  indexSource.slice(functionsStart, functionsEnd) +
    "\nconst event = input.event;" +
    "\nrenderBars(event, [], 40);" +
    "\nrenderMeta(event);" +
    "\nresult = {" +
    " staticResult," +
    " columnsAndRows: $('#bars').innerHTML," +
    " title: $('#latest-title').textContent," +
    " titleAria: $('#latest-title').getAttribute('aria-label')," +
    " detail: $('#latest-sub').textContent," +
    " sourceText: $('#race-source').textContent," +
    " sourceAria: $('#race-source').getAttribute('aria-label')," +
    " sourceHref: $('#race-source').href," +
    " metadata: $('#meta').innerHTML," +
    " more: $('#race-more').textContent," +
    " scenario: raceScenarioLabel(event, 0)," +
    " tab: racePollTabLabel(event)," +
    " compactDate: compactRacePollDate(event.fieldwork_end)," +
    " fieldwork: raceFieldworkRange(event.fieldwork_start, event.fieldwork_end)," +
    " comparisonState: $('#race-poll-panel').dataset.comparisonState," +
    " event" +
    "};",
  context
);
process.stdout.write(JSON.stringify(context.result));
"""


def run_race_glance_harness(href):
    event = {
        "pollster": "Ipsos",
        "fieldwork_start": "2026-09-02",
        "fieldwork_end": "2026-09-03",
        "publication_date": "2026-09-04",
        "sample_size": 1234,
        "source_url": "https://example.test/poll",
        "official_source_url": "",
        "hypothesis": "Hypothèse source Alpha",
        "candidates": [
            {"name": "Marine Le Pen", "score": 31.5},
            {"name": "Jean-Luc Mélenchon", "score": 14},
        ],
    }
    result = subprocess.run(
        ["node", "-e", RACE_GLANCE_HARNESS],
        cwd=ROOT,
        input=json.dumps({"href": href, "event": event}),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return event, json.loads(result.stdout)


class RaceGlanceDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = INDEX.read_text(encoding="utf-8")

    def test_packages_are_ranked_after_full_package_build(self):
        self.assertIn(
            "function raceComparableCandidateCount(",
            self.source,
        )
        self.assertIn(
            "function rankRacePollPackages(",
            self.source,
        )
        self.assertIn(
            "return packages;",
            self.source,
        )
        self.assertNotIn(
            "return packages.slice(0, 3);",
            self.source,
        )
        self.assertIn(
            "const allPollPackages =",
            self.source,
        )
        self.assertIn(
            "buildRacePollPackages(validEvents);",
            self.source,
        )
        self.assertIn(
            "const pollPackages = rankRacePollPackages(",
            self.source,
        )
        self.assertIn(
            "allPollPackages,",
            self.source,
        )
        self.assertIn(
            ").slice(0, 3);",
            self.source,
        )

    def test_newest_date_precedes_comparable_coverage_ranking(self):
        self.assertIn(
            "b.fieldwork_end.localeCompare(a.fieldwork_end)",
            self.source,
        )
        self.assertIn(
            "comparisonCountByPackage.get(b.key) -",
            self.source,
        )
        self.assertIn(
            "comparisonCountByPackage.get(a.key)",
            self.source,
        )

    def test_each_package_uses_its_most_comparable_scenario(self):
        self.assertIn(
            "raceGlanceState.selectedHypothesisByPoll[",
            self.source,
        )
        self.assertIn(
            "pollPackage.key",
            self.source,
        )
        self.assertIn(
            "] = selectedIndex;",
            self.source,
        )
        self.assertIn(
            'change.classification === "NO COMPARABLE PRIOR"',
            self.source,
        )

    def test_unavailable_comparisons_keep_column_visible(self):
        self.assertNotIn(
            '$("#race-poll-panel").classList.toggle(',
            self.source,
        )
        self.assertIn(
            'racePollPanel.classList.remove("is-no-comparison");',
            self.source,
        )
        self.assertIn(
            'hasPreviousDifference ? "available" : "unavailable"',
            self.source,
        )
        self.assertIn(
            '"dashboard.vs_previous_poll",',
            self.source,
        )
        self.assertIn('"VS PREV. POLL"', self.source)
        self.assertIn(
            'data-fr27-tooltip="${escapeAttribute(comparisonExplanation)}"',
            self.source,
        )


    def test_ranked_scenario_survives_dashboard_initialization(self):
        state_start = self.source.index(
            "raceGlanceState.scaleMax ="
        )
        loop_start = self.source.index(
            "pollPackages.forEach(pollPackage => {",
            state_start,
        )
        loop_end = self.source.index(
            "const selector =",
            loop_start,
        )
        initialization = self.source[
            loop_start:loop_end
        ]

        self.assertIn(
            "const selectedIndex = Number(",
            initialization,
        )
        self.assertIn(
            "raceGlanceState.selectedHypothesisByPoll[",
            initialization,
        )
        self.assertIn(
            "!Number.isInteger(selectedIndex)",
            initialization,
        )
        self.assertIn(
            "selectedIndex >= pollPackage.events.length",
            initialization,
        )
        self.assertNotIn(
            """pollPackages.forEach(pollPackage => {
          raceGlanceState.selectedHypothesisByPoll[pollPackage.key] = 0;
        });""",
            initialization,
        )

    def test_poll_tabs_show_compact_wave_identity(self):
        self.assertIn("full.textContent = fullLabel;", self.source)
        self.assertIn(
            "const shortLabel = racePollTabShortLabel(pollPackage);",
            self.source,
        )
        self.assertIn("short.textContent = shortLabel;", self.source)
        self.assertIn("button.setAttribute(\"aria-label\", fullLabel);", self.source)
        self.assertIn("button.dataset.fr27Tooltip = fullLabel;", self.source)

        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("Node.js is required for Race at a Glance tests")
        start = self.source.index("function racePollDate(")
        end = self.source.index("function raceScenarioLabel(", start)
        helpers = self.source[start:end]
        packages = [
            {"pollster": "Harris", "fieldwork_end": "2026-08-19"},
            {"pollster": "Harris", "fieldwork_end": "2026-08-22"},
            {
                "pollster": "Harris Interactive",
                "fieldwork_end": "2026-08-19",
            },
        ]
        script = (
            helpers
            + "\nconst packages = "
            + json.dumps(packages)
            + ";\nconsole.log(JSON.stringify({"
            + "full: packages.map(racePollTabLabel),"
            + "short: packages.map(racePollTabShortLabel)"
            + "}));"
        )
        result = subprocess.run(
            [node, "-e", script],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        labels = json.loads(result.stdout)
        full_labels = labels["full"]
        short_labels = labels["short"]

        self.assertEqual(
            [label.split()[-2:] for label in full_labels[:2]],
            [
                ["19", "Aug"],
                ["22", "Aug"],
            ],
        )
        self.assertTrue(
            all(label.startswith("Harris") for label in full_labels)
        )
        self.assertEqual(
            full_labels[2],
            "Harris Interactive · 19 Aug",
        )
        self.assertEqual(
            short_labels,
            [
                "Harris · 19 Aug",
                "Harris · 22 Aug",
                "Harris I. · 19 Aug",
            ],
        )
        self.assertEqual(
            len(full_labels),
            len(set(full_labels)),
        )
        self.assertEqual(
            len(short_labels),
            len(set(short_labels)),
        )

    def test_french_race_glance_localizes_ui_and_preserves_poll_data(self):
        event, result = run_race_glance_harness(
            "https://example.test/"
        )
        static = result["staticResult"]
        rows = result["columnsAndRows"]

        self.assertEqual(static["title"], "RAPPORT DE FORCE")
        self.assertEqual(static["scenario"], "SCÉNARIO")
        self.assertEqual(
            static["loadingAria"],
            "Chargement du dernier sondage",
        )
        self.assertIn("CANDIDAT", rows)
        self.assertIn("SCORE PUBLIÉ", rows)
        self.assertIn("RÉSULTAT", rows)
        self.assertIn("ÉCART PRÉC.", rows)
        self.assertEqual(result["fieldwork"], "2–3 sept. 2026")
        self.assertEqual(result["compactDate"], "3 sept.")
        self.assertEqual(
            result["title"],
            "Ipsos · Terrain 2–3 sept. 2026",
        )
        self.assertEqual(
            result["scenario"],
            "Scénario A · 2 candidats",
        )
        self.assertIn("Échantillon", result["detail"])
        self.assertRegex(result["detail"], r"1\s234")
        self.assertIn(
            "Pas de comparaison antérieure",
            result["detail"],
        )
        self.assertEqual(result["sourceText"], "Voir les résultats ↗")
        self.assertIn("Marine Le Pen", rows)
        self.assertIn("Jean-Luc Mélenchon", rows)
        self.assertIn("31.5%", rows)
        self.assertIn("14%", rows)
        self.assertIn("Hypothèse source Alpha", result["metadata"])
        self.assertEqual(result["event"], event)
        self.assertEqual(result["comparisonState"], "unavailable")
        self.assertNotIn(
            "race_glance.",
            json.dumps(result, ensure_ascii=False),
        )

    def test_english_race_glance_remains_unchanged_and_locale_aware(self):
        event, result = run_race_glance_harness(
            "https://example.test/?lang=en"
        )
        static = result["staticResult"]
        rows = result["columnsAndRows"]

        self.assertEqual(static["title"], "RACE AT A GLANCE")
        self.assertEqual(static["scenario"], "SCENARIO")
        self.assertIn("CANDIDATE", rows)
        self.assertIn("REPORTED SCORE", rows)
        self.assertIn("RESULT", rows)
        self.assertIn("VS PREV. POLL", rows)
        self.assertEqual(result["fieldwork"], "2–3 Sept 2026")
        self.assertEqual(result["compactDate"], "3 Sept")
        self.assertEqual(
            result["title"],
            "Ipsos · Fieldwork 2–3 Sept 2026",
        )
        self.assertEqual(
            result["scenario"],
            "Scenario A · 2 candidates",
        )
        self.assertIn("Sample 1,234", result["detail"])
        self.assertIn("No comparable prior event", result["detail"])
        self.assertEqual(result["sourceText"], "View full results ↗")
        self.assertIn("Marine Le Pen", rows)
        self.assertIn("Jean-Luc Mélenchon", rows)
        self.assertIn("31.5%", rows)
        self.assertIn("14%", rows)
        self.assertIn("Hypothèse source Alpha", result["metadata"])
        self.assertEqual(result["event"], event)
        self.assertNotIn(
            "race_glance.",
            json.dumps(result, ensure_ascii=False),
        )


if __name__ == "__main__":
    unittest.main()
