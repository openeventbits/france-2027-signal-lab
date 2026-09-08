from pathlib import Path
import json
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
HYBRID = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")
EN_SOURCE = (ROOT / "locales" / "en.js").read_text(encoding="utf-8")
FR_SOURCE = (ROOT / "locales" / "fr.js").read_text(encoding="utf-8")


def catalog(source):
    match = re.search(
        r"const messages = Object\.freeze\((\{.*?\})\);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("Locale catalog was not found")
    return json.loads(match.group(1))


POLL_COVERAGE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const indexSource = fs.readFileSync("index.html", "utf8");
const location = new URL(input.href);
const windowObject = {
  location,
  document: null,
  console: { warn() {} },
  addEventListener() {},
  setTimeout() {}
};
const context = {
  window: windowObject,
  globalThis: windowObject,
  URL,
  URLSearchParams,
  Intl,
  Date,
  Object,
  String,
  Number,
  Boolean,
  Set,
  Array
};

vm.runInNewContext(fs.readFileSync("locales/en.js", "utf8"), context);
vm.runInNewContext(fs.readFileSync("locales/fr.js", "utf8"), context);
vm.runInNewContext(fs.readFileSync("assets/localization.js", "utf8"), context);
context.FR27I18N = windowObject.FR27I18N;

const translateStart = indexSource.indexOf("    const translate =");
const translateEnd = indexSource.indexOf("    const agendaTopicLabel", translateStart);
vm.runInNewContext(indexSource.slice(translateStart, translateEnd), context);

const coverageStart = indexSource.indexOf("    function subtractCalendarMonths");
const coverageEnd = indexSource.indexOf("    function sourceNetworkMetrics", coverageStart);
vm.runInNewContext(indexSource.slice(coverageStart, coverageEnd), context);
context.dashboardState = { manifest: null };
const sourceStatusStart = coverageEnd;
const sourceStatusEnd = indexSource.indexOf("    function renderSourceNetworkStatus", sourceStatusStart);
vm.runInNewContext(indexSource.slice(sourceStatusStart, sourceStatusEnd), context);

vm.runInNewContext(`
  const twoPollsters = derivePollCoverage([
    { pollster: "Ifop", publication_date: "2026-07-01", fieldwork_end: "2026-06-30" },
    { pollster: "Ifop", publication_date: "2026-06-15", fieldwork_end: "2026-06-14" },
    { pollster: "Ipsos", publication_date: "2026-02-01", fieldwork_end: "2026-01-31" },
    { pollster: "Excluded old pollster", publication_date: "2025-12-31", fieldwork_end: "2025-12-30" }
  ]);
  const onePollster = derivePollCoverage([
    { pollster: "Ifop", publication_date: "2026-07-01", fieldwork_end: "2026-06-30" },
    { pollster: "Ifop", publication_date: "2026-06-15", fieldwork_end: "2026-06-14" }
  ]);
  const summarize = coverage => FR27I18N.t(
    "dashboard.poll_coverage_summary",
    { count: coverage.count }
  );
  const meta = coverage => FR27I18N.t(
    "dashboard.poll_coverage_meta",
    {
      startDate: formatContextDate(coverage.startDate),
      latestDate: formatContextDate(coverage.latestDate)
    }
  );
  const sourceStatus = deriveSourceNetworkStatus({
    discovery: { approved_publisher_domains: 42 },
    feed_coverage: {
      configured_feeds: 10,
      feeds_due_this_run: 5,
      feeds_successful_this_run: 5
    },
    election_news: []
  });
  result = {
    locale: FR27I18N.locale,
    localeTag: FR27I18N.localeTag,
    twoCount: twoPollsters.count,
    twoStart: twoPollsters.startDate,
    twoLatest: twoPollsters.latestDate,
    twoSummary: summarize(twoPollsters),
    oneSummary: summarize(onePollster),
    meta: meta(twoPollsters),
    sourceStatus
  };
`, context);

process.stdout.write(JSON.stringify(context.result));
"""


def run_poll_coverage(href):
    completed = subprocess.run(
        ["node", "-e", POLL_COVERAGE_HARNESS],
        cwd=ROOT,
        input=json.dumps({"href": href}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


class BatchALocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.en = catalog(EN_SOURCE)
        cls.fr = catalog(FR_SOURCE)

    def test_context_strip_approved_french(self):
        expected = {
            "dashboard.dashboard_context": "Contexte électoral",
            "dashboard.next_milestone": "PROCHAINE ÉCHÉANCE",
            "dashboard.latest_fieldwork": "DERNIER TERRAIN",
            "dashboard.poll_coverage": "SONDEURS RECENSÉS",
            "dashboard.source_network": "RÉSEAU DE SOURCES",
            "dashboard.target_first_round": "Cible : 1er tour",
            "dashboard.first_round_polling_coverage": (
                "Couverture des sondages du 1er tour"
            ),
        }
        for key, value in expected.items():
            self.assertEqual(self.fr[key], value)
            self.assertIn(f'"{key}"', INDEX)

    def test_poll_coverage_preserves_semantics_in_french(self):
        result = run_poll_coverage("https://example.test/")
        self.assertEqual(result["localeTag"], "fr-FR")
        self.assertEqual(result["twoCount"], 2)
        self.assertEqual(result["twoStart"], "2026-01-01")
        self.assertEqual(result["twoLatest"], "2026-07-01")
        self.assertEqual(
            result["twoSummary"],
            "2 sondeurs · fenêtre de 6 mois",
        )
        self.assertEqual(
            result["oneSummary"],
            "1 sondeur · fenêtre de 6 mois",
        )
        self.assertEqual(
            result["meta"],
            "1er tour · 1 janv. 2026–1 juil. 2026",
        )

    def test_poll_coverage_english_remains_equivalent(self):
        result = run_poll_coverage("https://example.test/?lang=en")
        self.assertEqual(result["localeTag"], "en-GB")
        self.assertEqual(result["twoCount"], 2)
        self.assertEqual(
            result["twoSummary"],
            "2 pollsters · 6-month window",
        )
        self.assertEqual(result["oneSummary"], "1 pollster · 6-month window")
        self.assertEqual(
            result["meta"],
            "First round · 1 Jan 2026–1 Jul 2026",
        )

    def test_signal_board_tabs_are_bilingual(self):
        keys = {
            "signal_board.candidates_847367c6": ("CANDIDATES", "CANDIDATS"),
            "signal_board.agenda": ("AGENDA", "AGENDA"),
            "signal_board.events": ("EVENTS", "ÉVÉNEMENTS"),
            "signal_board.issues": ("ISSUES", "ENJEUX"),
            "signal_board.runoff": ("RUNOFF", "2E TOUR"),
        }
        for key, (english, french) in keys.items():
            self.assertEqual(self.en[key], english)
            self.assertEqual(self.fr[key], french)
            self.assertIn(f'translate("{key}", "{english}")', HYBRID)

    def test_source_network_presentation_is_localized_but_state_is_stable(self):
        french = run_poll_coverage("https://example.test/")["sourceStatus"]
        english = run_poll_coverage(
            "https://example.test/?lang=en"
        )["sourceStatus"]
        self.assertEqual(french["visualState"], "operational")
        self.assertEqual(english["visualState"], "operational")
        self.assertEqual(french["status"], "OPÉRATIONNEL")
        self.assertEqual(english["status"], "OPERATIONAL")
        self.assertEqual(
            french["valueText"],
            "42 domaines approuvés",
        )
        self.assertEqual(
            english["valueText"],
            "42 approved publisher domains",
        )
        self.assertEqual(
            french["secondaryText"],
            "5/5 routes attendues ont abouti · 10 routes configurées",
        )

    def test_locale_does_not_change_signal_view_identity(self):
        view_block = HYBRID[
            HYBRID.index("  const views = Object.freeze({") :
            HYBRID.index("  const viewOrder = Object.keys(views);")
        ]
        identities = {
            "candidates": ("#signal-candidates", "signal-candidates-tab", "signal-candidates-panel"),
            "agenda": ("#signal-agenda", "signal-agenda-tab", "signal-agenda-panel"),
            "events": ("#signal-events", "signal-events-tab", "signal-events-panel"),
            "issues": ("#signal-issues", "signal-issues-tab", "signal-issues-panel"),
            "runoff": ("#signal-runoff", "signal-runoff-tab", "signal-runoff-panel"),
        }
        for key, values in identities.items():
            entry = view_block.split(f"    {key}: {{", 1)[1].split("\n    },", 1)[0]
            for value in values:
                self.assertIn(f'"{value}"', entry)
        self.assertIn(
            "const hashToView = new Map(viewOrder.map(key => [views[key].hash, key]));",
            HYBRID,
        )

    def test_hud_static_accessibility_and_tooltips_are_explicit(self):
        aria_keys = (
            "hud.system_dock",
            "hud.collapse_system_dock",
            "hud.live_time",
            "hud.election_countdown",
            "hud.infrastructure_methodology",
            "hud.source_universe",
            "hud.system_data_approach",
            "hud.dataset_scale",
            "hud.utility_links",
            "hud.open_github_repository",
            "hud.contact_signal_lab",
            "hud.share_current_view",
            "hud.project_information",
        )
        tooltip_keys = (
            "hud.collapse_system_dock",
            "hud.domains_explanation",
            "hud.polls_explanation",
            "hud.publishers_explanation",
            "hud.view_repository",
            "hud.contact",
            "hud.share_dashboard",
            "hud.about_signal_lab",
        )
        for key in aria_keys:
            self.assertIn(f'data-i18n-aria-label="{key}"', INDEX)
        for key in tooltip_keys:
            self.assertIn(f'data-i18n-fr27-tooltip="{key}"', INDEX)

    def test_runtime_hud_metrics_use_stable_keys_and_keep_values_unmarked(self):
        self.assertNotIn("function fr27HudExtractMetric", INDEX)
        self.assertIn('data-context-metric="approved_publisher_domains"', INDEX)
        for key in (
            "media_pulse.metric.accepted_news",
            "media_pulse.metric.publishers",
            "media_pulse.metric.recent_14d",
            "media_pulse.metric.candidate_watch",
        ):
            self.assertIn(f'fr27HudExtractExactMetric(\n        "{key}"', INDEX)

        for value_id in (
            "fr27-hud-domains-value",
            "fr27-hud-polls-value",
            "fr27-hud-news-value",
            "fr27-hud-publishers-value",
            "fr27-hud-recent-value",
            "fr27-hud-candidate-watch-value",
        ):
            tag = re.search(
                rf'<strong\b[^>]*\bid="{re.escape(value_id)}"[^>]*>',
                INDEX,
            )
            self.assertIsNotNone(tag)
            self.assertNotIn('data-i18n="', tag.group(0))

    def test_source_derived_evidence_and_legacy_comparison_remain_untranslated(self):
        self.assertIn('<h4 lang="fr">${escapeHtml(event.title)}</h4>', HYBRID)
        self.assertIn("<strong>${escapeHtml(observation.pollster)}</strong>", HYBRID)
        legacy_start = HYBRID.index("  function retainLegacyComparison()")
        legacy_end = HYBRID.index("\n\n  loadRunoffArchive();", legacy_start)
        legacy = HYBRID[legacy_start:legacy_end]
        self.assertIn(
            'summary.textContent = "Legacy middle layout — comparison only";',
            legacy,
        )
        self.assertNotIn("translate(", legacy)


if __name__ == "__main__":
    unittest.main()
