from pathlib import Path
import json
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
HYBRID_JS = ROOT / "assets" / "hybrid-dashboard.js"


def run_media_model_script(payload, expression):
    script = r"""
const fs = require("fs");
const vm = require("vm");
let source = fs.readFileSync(
  "assets/hybrid-dashboard.js",
  "utf8"
);
source = source.replace(
  /\s+retainLegacyComparison\(\);\s+renderAll\(\);\s+window\.addEventListener\("hashchange", handleSignalHashChange\);\s+document\.addEventListener\("hybrid:dataset", renderAll\);/,
  ""
);
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const payload = input.payload;
const mount = {};
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
    getElementById(id) {
      return id === "hybrid-signal-board" ? mount : null;
    },
    addEventListener() {},
    querySelector() { return null; }
  },
  dashboardState: {
    loadState: { news: "ready" },
    news: payload
  },
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
        input=json.dumps(
            {"payload": payload, "expression": expression}
        ),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


class FinalDashboardShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.js = HYBRID_JS.read_text(encoding="utf-8")

    def test_top_row_contains_three_primary_panels(self):
        changed = self.html.index(
            'class="panel what-changed"'
        )
        race = self.html.index(
            'class="panel race-glance"'
        )
        media = self.html.index(
            'class="panel top-media-pulse"'
        )
        context = self.html.index(
            'class="context-strip"'
        )

        self.assertLess(changed, race)
        self.assertLess(race, media)
        self.assertLess(media, context)

    def test_top_media_mount_uses_existing_media_model(self):
        self.assertIn(
            "renderTopMediaPulse(models.media, models.agenda);",
            self.js,
        )

        self.assertNotIn(
            "renderTopMediaPulse(models.media);",
            self.js,
        )

    def test_summary_cards_are_removed_from_primary_render(self):
        start = self.js.index(
            "function renderAll(event = null)"
        )
        end = self.js.index(
            "function handleSignalHashChange",
            start,
        )
        renderer = self.js[start:end]

        self.assertIn(
            "renderFocusWorkspace(models)",
            renderer,
        )
        self.assertNotIn(
            "renderSummaryGrid(models)",
            renderer,
        )
        self.assertNotIn(
            "Four summaries",
            renderer,
        )

    def test_media_topic_navigation_supports_top_mount(self):
        for contract in (
            "function bindTopicCoverageModal(",
            "mediaModel,",
            "agendaModel",
            "[data-topic-coverage-open]",
            "[data-hybrid-media-topic]",
            "[data-hybrid-media-candidate]",
            "France2027TopicCoverageModal",
            "bindTopicCoverageModal(model, agendaModel);",
        ):
            self.assertIn(contract, self.js)

        self.assertNotIn(
            "bindMediaTopicLinks(topMediaMount);",
            self.js,
        )

    def test_module_navigation_includes_poll_compare(self):
        self.assertIn(
            "data-hybrid-poll-compare",
            self.js,
        )
        self.assertIn(
            ">POLL COMPARE</button>",
            self.js,
        )
        self.assertIn(
            '"polling-evidence-lab"',
            self.js,
        )

    def test_three_column_and_five_module_layout_are_locked(self):
        self.assertIn(
            "/* FINAL DASHBOARD V2 SHELL */",
            self.html,
        )
        self.assertIn(
            "max-width: 1780px;",
            self.html,
        )
        self.assertIn(
            "minmax(470px, .98fr)",
            self.html,
        )
        self.assertIn(
            "minmax(560px, 1.24fr);",
            self.html,
        )
        self.assertIn(
            "minmax(250px, 1.08fr);",
            self.html,
        )
        self.assertIn(
            "repeat(5, minmax(0, 1fr));",
            self.html,
        )


    def test_top_media_typography_is_one_step_below_neighbors(self):
        headline_start = self.html.index(
            ".top-media-coverage-headline"
        )
        headline_end = self.html.index(
            ".top-media-source-link",
            headline_start,
        )
        headline_css = self.html[
            headline_start:headline_end
        ]

        shift_start = self.html.index(
            ".top-media-shift-name"
        )
        shift_end = self.html.index(
            ".top-media-shift-row > strong",
            shift_start,
        )
        shift_css = self.html[
            shift_start:shift_end
        ]

        metadata_start = self.html.index(
            ".top-media-coverage-meta time"
        )
        metadata_end = self.html.index(
            ".top-media-coverage-meta strong",
            metadata_start,
        )
        metadata_css = self.html[
            metadata_start:metadata_end
        ]

        self.assertIn(
            "font-size: 10px;",
            headline_css,
        )
        self.assertIn(
            "font-size: 9px;",
            shift_css,
        )
        self.assertIn(
            "font-size: 8px;",
            metadata_css,
        )


    def test_top_media_renderer_limits_coverage_and_forbids_images(self):
        start = self.js.index(
            "function renderTopMediaPulsePanel("
        )
        end = self.js.index(
            "function renderTopMediaPulse(",
            start,
        )
        renderer = self.js[start:end]

        self.assertIn(
            ".slice(0, 5)",
            renderer,
        )
        self.assertIn(
            'class="top-media-coverage-row"',
            renderer,
        )
        self.assertIn(
            "Open source",
            renderer,
        )
        self.assertNotIn(
            "<img",
            renderer,
        )
        self.assertNotIn(
            "thumbnail",
            renderer.lower(),
        )
        self.assertNotIn(
            "portrait",
            renderer.lower(),
        )

    def test_top_media_header_contains_four_prominent_metrics(self):
        start = self.js.index(
            "function renderTopMediaPulse(model, agendaModel)"
        )

        end = self.js.index(
            "function bindPollCompareShortcut",
            start,
        )

        section = self.js[start:end]

        for contract in (
            "const metrics = [",
            "value: model.electionNewsCount",
            "model.acceptedNewsPublisherCount",
            "value: model.activityItemCount",
            "value: model.candidateWatchCount",
            'label: "accepted news"',
            'label: "publishers"',
            'label: "recent (14d)"',
            'label: "candidate-watch"',
            'class="top-media-header-metric"',
        ):
            self.assertIn(contract, section)

    def test_media_model_derives_ranked_top_publishers(self):
        start = self.js.index(
            "function buildMediaViewModel()"
        )
        end = self.js.index(
            "function buildAgendaViewModel()",
            start,
        )
        model = self.js[start:end]

        self.assertIn(
            "const publisherCounts =",
            model,
        )
        self.assertIn(
            "const topPublishers =",
            model,
        )
        self.assertIn(
            ".slice(0, 5);",
            model,
        )
        self.assertIn(
            "topPublishers,",
            model,
        )

    def test_top_media_contains_mockup_sections(self):
        start = self.js.index(
            "function renderTopMediaPulsePanel("
        )
        end = self.js.index(
            "function renderTopMediaPulse(",
            start,
        )
        renderer = self.js[start:end]

        for label in (
            "Latest election coverage",
            "Coverage shift",
            "Topic coverage",
            "Top publishers",
        ):
            self.assertIn(
                label,
                renderer,
            )


    def test_top_media_uses_mockup_visual_cues(self):
        self.assertIn(
            "30-day activity · 14-day recent",
            self.html,
        )
        self.assertIn(
            "/* MOCKUP VISUAL CUES — TOP MEDIA PULSE */",
            self.html,
        )
        self.assertIn(
            "height: 455px;",
            self.html,
        )
        self.assertIn(
            'content: "Δ pp";',
            self.html,
        )
        self.assertIn(
            ".top-media-publisher-row:nth-child(2)",
            self.html,
        )
        self.assertIn(
            "grid-template-columns: minmax(0, 1fr);",
            self.html[
                self.html.index(
                    ".top-media-coverage-row {"
                ):
                self.html.index(
                    ".top-media-coverage-row::before"
                )
            ],
        )

        renderer_start = self.js.index(
            "function renderTopMediaPulsePanel("
        )
        renderer_end = self.js.index(
            "function renderTopMediaPulse(",
            renderer_start,
        )
        renderer = self.js[
            renderer_start:renderer_end
        ]

        self.assertNotIn("<img", renderer)
        self.assertNotIn(
            "thumbnail",
            renderer.lower(),
        )


    def test_coverage_shift_uses_adjacent_period_segments(self):
        renderer_start = self.js.index(
            "function renderTopMediaPulsePanel("
        )
        renderer_end = self.js.index(
            "function renderTopMediaPulse(",
            renderer_start,
        )
        renderer = self.js[
            renderer_start:renderer_end
        ]

        self.assertIn(
            "const maxCombinedShare = Math.max(",
            renderer,
        )
        self.assertIn(
            "item.latestShare +",
            renderer,
        )
        self.assertIn(
            "item.previousShare",
            renderer,
        )
        self.assertIn(
            "--top-prior-share:${previousWidth.toFixed(2)}%",
            renderer,
        )
        self.assertIn(
            'class="top-media-shift-prior-value"',
            renderer,
        )
        self.assertIn(
            "${previousShareText}%",
            renderer,
        )
        self.assertNotIn(
            "previousPosition",
            renderer,
        )
        self.assertNotIn(
            "maxCandidateShare",
            renderer,
        )
        self.assertNotIn(
            "Candidate-linked articles",
            renderer,
        )

        css_start = self.html.index(
            "/* MOCKUP COVERAGE SHIFT — "
            "ADJACENT PERIOD SEGMENTS */"
        )
        css = self.html[css_start:]

        self.assertIn(
            "display: flex;",
            css,
        )
        self.assertIn(
            "flex: 0 0 var(--top-current-share);",
            css,
        )
        self.assertIn(
            "flex: 0 0 var(--top-prior-share);",
            css,
        )
        self.assertIn(
            ".top-media-shift-prior-value",
            css,
        )
        self.assertIn(
            "content: none;",
            css,
        )
        self.assertIn(
            ".is-prior i::before",
            css,
        )


    def test_top_media_reserves_visible_topic_and_publisher_space(self):
        marker = (
            "/* TOP MEDIA SUPPORT VISIBILITY */"
        )
        start = self.html.index(marker)
        css = self.html[start:]

        self.assertIn(
            """.top-media-analysis {
      grid-template-rows:
        minmax(0, 1fr)
        142px;""",
            css,
        )
        self.assertIn(
            """.top-media-support-grid {
      height: 142px;
      min-height: 142px;
      max-height: 142px;""",
            css,
        )
        self.assertIn(
            """.top-media-topic-list,
    .top-media-publisher-list {
      max-height: 112px;""",
            css,
        )
        self.assertIn(
            "overflow-y: auto;",
            css,
        )
        self.assertIn(
            "scrollbar-width: thin;",
            css,
        )
        self.assertIn(
            ".top-media-topic-list::-webkit-scrollbar",
            css,
        )
        self.assertIn(
            """.top-media-topic-row,
    .top-media-publisher-row {
      min-height: 21px;""",
            css,
        )


    def test_candidate_coverage_aliases_are_canonicalized(self):
        for contract in (
            "function buildMediaCandidateCanonicalizer",
            "suffixMatches",
            "canonicalizeCandidate",
            "candidateCoverage:",
            "latestItems:",
            "previousItems:",
        ):
            self.assertIn(contract, self.js)

    def test_top_candidate_shift_rows_open_combined_dialog(self):
        position = self.js.index(
            "data-hybrid-media-candidate"
        )
        context = self.js[position - 220:position + 420]

        for contract in (
            'type="button"',
            'aria-haspopup="dialog"',
            'aria-controls="topic-coverage-modal"',
            'aria-expanded="false"',
        ):
            self.assertIn(contract, context)

        self.assertIn(
            "Open coverage analysis →",
            self.js,
        )


    def test_exact_dashboard_cta_component_scope(self):
        class_attributes = re.findall(
            r'class="([^"]*\bmedia-pulse-dashboard-cta\b[^"]*)"',
            self.html + "\n" + self.js,
        )

        self.assertCountEqual(
            class_attributes,
            [
                "media-pulse-dashboard-cta",
                "top-media-panel-link ecm-open media-pulse-dashboard-cta",
                "top-media-panel-link tcm-open media-pulse-dashboard-cta",
            ],
        )
        self.assertRegex(
            self.html,
            re.compile(
                r'<a\s+id="race-source"\s+'
                r'class="media-pulse-dashboard-cta"',
                re.DOTALL,
            ),
        )

    def test_media_pulse_rerender_is_news_lane_aware(self):
        start = self.js.index(
            "function renderAll(event = null)"
        )
        end = self.js.index(
            "function handleSignalHashChange",
            start,
        )
        renderer = self.js[start:end]

        guarded_render = re.search(
            r'const datasetLane = event\?\.detail\?\.name \|\| "";'
            r'.*?if \(!datasetLane \|\| datasetLane === "news"\)\s*\{'
            r'\s*renderTopMediaPulse\(models\.media, models\.agenda\);'
            r'\s*\}',
            renderer,
            re.DOTALL,
        )
        self.assertIsNotNone(guarded_render)
        self.assertGreater(
            renderer.index("mount.innerHTML"),
            guarded_render.end(),
        )
        self.assertIn("renderAll();", self.js)
        self.assertIn(
            'document.addEventListener("hybrid:dataset", renderAll);',
            self.js,
        )

    def test_dashboard_cta_component_is_narrow_and_non_global(self):
        start = self.html.index(
            ".media-pulse-dashboard-cta {"
        )
        end = self.html.index(
            ".top-media-shift",
            start,
        )
        component = self.html[start:end]

        for contract in (
            "appearance: none;",
            "display: inline-flex;",
            "width: max-content;",
            "min-height: 16px;",
            "padding: 1px 0;",
            "font-size: 10px;",
            "font-weight: 700;",
            "line-height: 1.3;",
            ".media-pulse-dashboard-cta:focus-visible",
        ):
            self.assertIn(contract, component)

        self.assertNotRegex(
            component,
            re.compile(r"(?m)^\s*(button|a|h2|\*)\s*\{"),
        )
        self.assertNotIn("!important", component)



    @staticmethod
    def candidate_payload(current_count=10, prior_count=10):
        publishers = [f"Publisher {index}" for index in range(5)]
        records = []
        for period, count, published_at in (
            ("current", current_count, "2026-07-26T12:00:00Z"),
            ("prior", prior_count, "2026-07-19T12:00:00Z"),
        ):
            for index in range(count):
                records.append(
                    {
                        "id": f"{period}-{index}",
                        "publisher": publishers[index % len(publishers)],
                        "published_at": published_at,
                        "url": f"https://example.test/{period}-{index}",
                        "candidates": [
                            "Candidate A"
                            if period == "current" or index < count / 2
                            else "Candidate B"
                        ],
                    }
                )
        return {
            "generated_at": "2026-07-26T20:35:00Z",
            "window_days": 30,
            "counts": {"election_news": 0},
            "election_news": [],
            "candidate_watch": records,
            "campaign_agenda": {"topics": []},
        }

    def test_valid_backend_candidate_visibility_is_preferred(self):
        result = run_media_model_script(
            self.candidate_payload(),
            """(() => {
              const derived = api.deriveCandidateVisibility(payload);
              const backend = {
                comparison_quality: derived.comparison_quality,
                prior_period: derived.prior_period,
                current_period: derived.current_period,
                method: derived.method
              };
              payload.candidate_visibility = backend;
              return {
                preferred:
                  api.resolveCandidateVisibility(payload) === backend,
                valid:
                  api.isValidCandidateVisibility(backend, payload)
              };
            })()""",
        )
        self.assertEqual(result, {"preferred": True, "valid": True})

    def test_missing_candidate_visibility_uses_deterministic_fallback(self):
        result = run_media_model_script(
            self.candidate_payload(9, 10),
            """(() => {
              const first = api.resolveCandidateVisibility(payload);
              const second = api.resolveCandidateVisibility(payload);
              return {
                sameValue: JSON.stringify(first) === JSON.stringify(second),
                current: first.current_period,
                prior: first.prior_period,
                quality: first.comparison_quality
              };
            })()""",
        )
        self.assertTrue(result["sameValue"])
        self.assertEqual(result["current"]["start_date"], "2026-07-20")
        self.assertEqual(result["current"]["end_date"], "2026-07-26")
        self.assertEqual(result["prior"]["start_date"], "2026-07-13")
        self.assertEqual(result["prior"]["end_date"], "2026-07-19")
        self.assertEqual(result["quality"]["reason"], "insufficient_data")

    def test_malformed_backend_candidate_visibility_uses_fallback(self):
        result = run_media_model_script(
            self.candidate_payload(),
            """(() => {
              payload.candidate_visibility = {
                method: "share_of_candidate_linked_records",
                comparison_quality: { status: "comparable" }
              };
              const resolved = api.resolveCandidateVisibility(payload);
              return {
                malformedRejected:
                  resolved !== payload.candidate_visibility,
                status: resolved.comparison_quality.status
              };
            })()""",
        )
        self.assertEqual(
            result,
            {"malformedRejected": True, "status": "comparable"},
        )

    def test_non_comparable_candidate_rows_expose_unavailable_change(self):
        result = run_media_model_script(
            self.candidate_payload(9, 10),
            """(() => {
              const model = api.buildMediaViewModel();
              return {
                quality: model.comparisonQuality,
                rows: model.candidateCoverage.map(item => ({
                  changeAvailable: item.changeAvailable,
                  delta: item.delta,
                  changePp: item.changePp,
                  direction: item.direction
                }))
              };
            })()""",
        )
        self.assertEqual(result["quality"]["status"], "not_comparable")
        self.assertTrue(result["rows"])
        for row in result["rows"]:
            self.assertFalse(row["changeAvailable"])
            self.assertIsNone(row["delta"])
            self.assertIsNone(row["changePp"])
            self.assertEqual(row["direction"], "unavailable")

    def test_comparable_candidate_rows_preserve_actual_delta(self):
        result = run_media_model_script(
            self.candidate_payload(),
            """(() => {
              const model = api.buildMediaViewModel();
              const candidate = model.candidateCoverage.find(
                item => item.name === "Candidate A"
              );
              return {
                status: model.comparisonQuality.status,
                changeAvailable: candidate.changeAvailable,
                delta: candidate.delta,
                changePp: candidate.changePp,
                direction: candidate.direction
              };
            })()""",
        )
        self.assertEqual(result["status"], "comparable")
        self.assertTrue(result["changeAvailable"])
        self.assertEqual(result["delta"], 50)
        self.assertEqual(result["changePp"], 50)
        self.assertEqual(result["direction"], "positive")


if __name__ == "__main__":
    unittest.main()
