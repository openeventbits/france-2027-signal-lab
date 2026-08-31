from pathlib import Path
from datetime import date, timedelta
import json
import re
import subprocess
import unittest

from test_candidate_signals_frontend import run_candidate_module


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
  formatRunoffFieldwork: value => String(value),
  safeSourceUrl: value => String(value)
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
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def agenda_evolution_payload():
    start = date(2026, 7, 10)

    dates = [
        (
            start + timedelta(days=index)
        ).isoformat()
        for index in range(30)
    ]

    definitions = [
        (
            "selection_strategy",
            "Primaries & party strategy",
            99,
            1,
            10,
        ),
        (
            "candidacies_endorsements",
            "Candidacies & endorsements",
            98,
            8,
            2,
        ),
        (
            "legal_eligibility",
            "Legal cases & eligibility",
            97,
            1,
            6,
        ),
        (
            "polls_race",
            "Polling & race narratives",
            96,
            5,
            1,
        ),
        (
            "rules_calendar",
            "Rules, calendar & campaign mechanics",
            95,
            4,
            1,
        ),
    ]

    legacy_topics = []
    evolution_topics = []

    for (
        topic_id,
        label,
        legacy_source_days,
        previous_total,
        latest_total,
    ) in definitions:
        counts = [0] * 30

        # Previous comparison window:
        # 25–31 July = indices 15–21.
        counts[15] = previous_total

        # Latest comparison window:
        # 1–7 August = indices 22–28.
        if latest_total >= 7:
            base = latest_total // 7
            remainder = latest_total % 7

            for offset in range(7):
                counts[22 + offset] = (
                    base +
                    (
                        1
                        if offset < remainder
                        else 0
                    )
                )
        else:
            for offset in range(
                latest_total
            ):
                counts[22 + offset] = 1

        daily = [
            {
                "date": day,
                "item_count": count,
                "source_day_count": count,
            }
            for day, count in zip(
                dates,
                counts,
            )
        ]

        evolution_source_days = sum(
            counts
        )

        active_days = sum(
            count > 0
            for count in counts
        )

        legacy_topics.append(
            {
                "id": topic_id,
                "label": label,
                "item_count": legacy_source_days,
                "publisher_count": 5,
                "publisher_names": [
                    "Publisher A",
                    "Publisher B",
                ],
                "source_day_count": (
                    legacy_source_days
                ),
                "active_day_count": 14,
                "display_eligible": True,
                "supporting_item_count": 1,
                "omitted_item_count": 0,
                "supporting_items": [
                    {
                        "id": (
                            f"{topic_id}-evidence"
                        ),
                        "publisher": (
                            "Publisher A"
                        ),
                        "published_at": (
                            "2026-08-07T12:00:00Z"
                        ),
                        "headline": (
                            f"{label} evidence"
                        ),
                        "url": (
                            "https://example.test/evidence"
                        ),
                        "candidates": [],
                        "matched_terms": [
                            "example term"
                        ],
                    }
                ],
            }
        )

        evolution_topics.append(
            {
                "id": topic_id,
                "label": label,
                "item_count": (
                    evolution_source_days
                ),
                "publisher_count": 5,
                "source_day_count": (
                    evolution_source_days
                ),
                "active_day_count": (
                    active_days
                ),
                "display_eligible": True,
                "daily_activity": daily,
                "matched_term_counts": [
                    {
                        "term": (
                            "example term"
                        ),
                        "item_count": max(
                            1,
                            evolution_source_days,
                        ),
                    }
                ],
            }
        )

    return {
        "generated_at": (
            "2026-08-08T02:30:00Z"
        ),
        "window_days": 30,
        "campaign_agenda": {
            "window_days": 30,
            "input_item_count": 100,
            "classified_item_count": 50,
            "unclassified_item_count": 50,
            "method": (
                "accepted_relevant_news_by_campaign_theme"
            ),
            "display_min_source_days": 2,
            "topics": legacy_topics,
            "evolution": {
                "period_days": 30,
                "period_start": (
                    "2026-07-10"
                ),
                "period_end": (
                    "2026-08-08"
                ),
                "period_end_partial": True,
                "comparison_days": 7,
                "latest_start": (
                    "2026-08-01"
                ),
                "latest_end": (
                    "2026-08-07"
                ),
                "previous_start": (
                    "2026-07-25"
                ),
                "previous_end": (
                    "2026-07-31"
                ),
                "topics": evolution_topics,
            },
        },
    }


class FinalDashboardShellTests(unittest.TestCase):
    def test_agenda_movement_threshold_boundaries(self):
        payload = agenda_evolution_payload()

        result = run_media_model_script(
            payload,
            """({
              rising: api.agendaMovementLabel(4, 2, 5),
              fading: api.agendaMovementLabel(2, 4, -5),
              stableShare: api.agendaMovementLabel(4, 2, 4.9),
              stableDelta: api.agendaMovementLabel(3, 2, 5),
              stableActivity: api.agendaMovementLabel(2, 2, 6)
            })""",
        )

        self.assertEqual(
            result,
            {
                "rising": "RISING",
                "fading": "FADING",
                "stableShare": "STABLE",
                "stableDelta": "STABLE",
                "stableActivity": "STABLE",
            },
        )

    def test_agenda_structure_threshold_boundaries(self):
        payload = agenda_evolution_payload()

        result = run_media_model_script(
            payload,
            """({
              eventDriven: api.agendaStructureLabel(14, 20, 0.40, 5),
              persistent14: api.agendaStructureLabel(7, 7, 0.39, 5),
              persistent30: api.agendaStructureLabel(6, 12, 0.39, 5),
              intermittent: api.agendaStructureLabel(6, 11, 0.39, 5),
              eventPrecedence: api.agendaStructureLabel(14, 20, 0.50, 8)
            })""",
        )

        self.assertEqual(
            result["eventDriven"],
            "EVENT-DRIVEN",
        )

        self.assertEqual(
            result["persistent14"],
            "PERSISTENT",
        )

        self.assertEqual(
            result["persistent30"],
            "PERSISTENT",
        )

        self.assertEqual(
            result["intermittent"],
            "INTERMITTENT",
        )

        self.assertEqual(
            result["eventPrecedence"],
            "EVENT-DRIVEN",
        )

    def test_agenda_evolution_model_keeps_legacy_topics_isolated(self):
        payload = agenda_evolution_payload()

        result = run_media_model_script(
            payload,
            """(() => {
              const model = api.buildAgendaViewModel();
              return {
                ready: model.evolutionReady,
                legacyFirst: {
                  id: model.topics[0].id,
                  sourceDays: model.topics[0].source_day_count
                },
                evolutionFirst: {
                  id: model.evolutionTopics[0].id,
                  sourceDays: model.evolutionTopics[0].source_day_count
                }
              };
            })()""",
        )

        self.assertTrue(
            result["ready"]
        )

        # Shared Agenda model values stay
        # legacy-authoritative for Media Pulse.
        self.assertEqual(
            result["legacyFirst"],
            {
                "id": (
                    "selection_strategy"
                ),
                "sourceDays": 99,
            },
        )

        # Agenda Evolution uses its own
        # exact-calendar projection.
        self.assertEqual(
            result["evolutionFirst"],
            {
                "id": (
                    "selection_strategy"
                ),
                "sourceDays": 11,
            },
        )

    def test_agenda_evolution_builds_exact_six_five_day_bins(self):
        payload = agenda_evolution_payload()

        result = run_media_model_script(
            payload,
            """(() => {
              const model = api.buildAgendaViewModel();
              const topic = model.evolutionTopics.find(
                item => item.id === "selection_strategy"
              );
              return {
                bins: topic.bins,
                total: topic.source_day_count
              };
            })()""",
        )

        self.assertEqual(
            len(result["bins"]),
            6,
        )

        self.assertEqual(
            result["bins"][0]["start"],
            "2026-07-10",
        )

        self.assertEqual(
            result["bins"][0]["end"],
            "2026-07-14",
        )

        self.assertEqual(
            result["bins"][-1]["start"],
            "2026-08-04",
        )

        self.assertEqual(
            result["bins"][-1]["end"],
            "2026-08-08",
        )

        self.assertEqual(
            sum(
                item["sourceDays"]
                for item
                in result["bins"]
            ),
            result["total"],
        )

    def test_agenda_diagnostics_use_latest_complete_periods(self):
        payload = agenda_evolution_payload()

        result = run_media_model_script(
            payload,
            """(() => {
              const model = api.buildAgendaViewModel();
              return {
                diagnostics: model.diagnostics,
                movement: Object.fromEntries(
                  model.evolutionTopics.map(
                    topic => [
                      topic.id,
                      topic.movement
                    ]
                  )
                )
              };
            })()""",
        )

        diagnostics = result[
            "diagnostics"
        ]

        self.assertEqual(
            diagnostics[
                "activeTopics"
            ],
            5,
        )

        self.assertAlmostEqual(
            diagnostics[
                "top3Share"
            ],
            90.0,
            places=6,
        )

        self.assertEqual(
            diagnostics[
                "risingTopics"
            ],
            2,
        )

        self.assertEqual(
            diagnostics[
                "top3Turnover"
            ],
            2,
        )

        self.assertEqual(
            diagnostics[
                "top3TurnoverDenominator"
            ],
            3,
        )

        self.assertEqual(
            result["movement"][
                "selection_strategy"
            ],
            "RISING",
        )

        self.assertEqual(
            result["movement"][
                "legal_eligibility"
            ],
            "RISING",
        )

        self.assertEqual(
            result["movement"][
                "candidacies_endorsements"
            ],
            "FADING",
        )

    def test_agenda_model_falls_back_when_evolution_is_absent(self):
        payload = agenda_evolution_payload()

        del payload[
            "campaign_agenda"
        ]["evolution"]

        result = run_media_model_script(
            payload,
            """(() => {
              const model = api.buildAgendaViewModel();
              return {
                state: model.state,
                ready: model.evolutionReady,
                topicCount: model.topics.length,
                evolutionCount: model.evolutionTopics.length
              };
            })()""",
        )

        self.assertEqual(
            result["state"],
            "ready",
        )

        self.assertFalse(
            result["ready"]
        )

        self.assertEqual(
            result["topicCount"],
            5,
        )

        self.assertEqual(
            result["evolutionCount"],
            0,
        )

    def test_agenda_evolution_renderer_exposes_full_workspace(self):
        payload = agenda_evolution_payload()

        html = run_media_model_script(
            payload,
            """(() => {
              const model = api.buildAgendaViewModel();
              return api.renderAgendaPanel(model);
            })()""",
        )

        for contract in (
            "AGENDA MONITOR",
            "AGENDA EVOLUTION",
            "TOPIC DOSSIER",
            "ACTIVE TOPICS",
            "TOP-3 SHARE",
            "RISING TOPICS",
            "TOP-3 TURNOVER",
            "30-DAY EVOLUTION",
            "WEEK SHIFT",
            "SELECTED RECURRING TOPIC",
            "ASSOCIATED SIGNALS",
            "RECENT EVIDENCE",
            "ACTIVITY PROFILE",
        ):
            self.assertIn(contract, html)

        self.assertEqual(
            html.count('data-agenda-day-cell="true"'),
            150,
        )

        self.assertEqual(
            html.count('data-agenda-activity-day="true"'),
            30,
        )

        self.assertEqual(
            html.count('data-hybrid-agenda-topic='),
            10,
        )

        self.assertGreaterEqual(
            html.count('aria-pressed="true"'),
            2,
        )

        self.assertNotIn("Eligible-topic ranking", html)
        self.assertNotIn("undefined/30", html)
        self.assertIn("hybrid-agenda-v6-info", html)
        self.assertIn("Source-day = unique publisher", html)

        self.assertEqual(
            html.count('data-agenda-scroll-region='),
            2,
        )

        for legend in (
            "OLDER",
            "PRIOR 7D",
            "LATEST 7D",
            "PARTIAL DAY",
        ):
            self.assertIn(legend, html)

        self.assertNotIn("MOVEMENT PROFILE", html)
        self.assertNotIn("hybrid-agenda-v4-", html)

        for title in (
            "AGENDA MONITOR",
            "AGENDA EVOLUTION",
            "TOPIC DOSSIER",
        ):
            self.assertRegex(
                html,
                rf'<h3[^>]+data-fr27-type="panel-title"[^>]*>{title}</h3>',
            )
        for title in (
            "30-DAY EVOLUTION",
            "WEEK SHIFT",
            "ACTIVITY PROFILE",
            "ASSOCIATED SIGNALS",
            "RECENT EVIDENCE",
        ):
            self.assertIn(
                f'data-fr27-type="module-title">{title}',
                html,
            )
        self.assertIn('data-fr27-type="item-title"', html)
        self.assertIn('data-fr27-type="row-label"', html)
        self.assertIn('data-fr27-type="scale-label"', html)
        self.assertIn('data-fr27-type="key-data"', html)
        self.assertIn('data-fr27-type="data"', html)
        self.assertIn('data-fr27-type="status-label"', html)

    def test_media_issues_and_events_render_semantic_typography(self):
        news = json.loads(
            (ROOT / "news_wire.json").read_text(encoding="utf-8")
        )
        rendered = run_media_model_script(
            news,
            """(() => {
              const mediaModel = api.buildMediaViewModel();
              const mediaWithComparison = {
                ...mediaModel,
                candidateCoverageAvailable: true,
                candidateCoverageLeaders: [{
                  name: "Candidate A",
                  tierLabel: "MAIN FIELD",
                  latestShare: 25,
                  previousShare: 20,
                  delta: 5,
                  changeAvailable: true,
                  latestCount: 5,
                  previousCount: 4
                }]
              };
              return {
                media: api.renderMediaPanel(mediaWithComparison),
                issues: api.renderIssuesPanel(api.buildPolicyAgendaViewModel())
              };
            })()""",
        )

        media = rendered["media"]
        self.assertRegex(
            media,
            r'class="hybrid-candidate-share-name" data-fr27-type="row-label"',
        )
        self.assertIn(
            'class="hybrid-status-chip" data-fr27-type="status-label"',
            media,
        )
        self.assertIn('<strong data-fr27-type="data">25%</strong>', media)
        self.assertIn('data-fr27-type="scale-label"', media)
        self.assertIn('data-fr27-type="module-title"', media)

        issues = rendered["issues"]
        for title in (
            "POLICY MONITOR",
            "ISSUE EVOLUTION",
            "ISSUE DOSSIER",
        ):
            self.assertRegex(
                issues,
                rf'data-fr27-type="panel-title">\s*{title}',
            )
        for role in (
            "module-title",
            "item-title",
            "row-label",
            "scale-label",
            "key-data",
            "data",
            "status-label",
        ):
            self.assertIn(f'data-fr27-type="{role}"', issues)

        events = json.loads(
            (ROOT / "campaign_events.json").read_text(encoding="utf-8")
        )
        event_html = run_media_model_script(
            events,
            """(() => {
              context.dashboardState.campaignEvents = payload;
              context.dashboardState.loadState.campaignEvents = "loaded";
              return api.renderEventsPanel(api.buildEventsViewModel());
            })()""",
        )
        for title in (
            "12-WEEK SCHEDULE",
            "UPCOMING EVENTS",
            "EVENT DOSSIER",
            "SCHEDULE WATCH",
        ):
            self.assertIn(
                f'data-fr27-type="panel-title">{title}',
                event_html,
            )
        self.assertRegex(
            event_html,
            r'class="hybrid-events-ops-months"[^>]*>.*?data-fr27-type="scale-label"',
        )
        self.assertRegex(
            event_html,
            r'<time data-fr27-type="scale-label" datetime=',
        )
        self.assertIn('data-fr27-type="item-title"', event_html)
        self.assertIn('data-fr27-type="field-label"', event_html)
        self.assertIn('data-fr27-type="status-label"', event_html)

    def test_agenda_renderer_keeps_legacy_fallback_without_evolution(self):
        payload = agenda_evolution_payload()

        del payload[
            "campaign_agenda"
        ]["evolution"]

        html = run_media_model_script(
            payload,
            """(() => {
              const model = api.buildAgendaViewModel();
              return api.renderAgendaPanel(model);
            })()""",
        )

        self.assertIn(
            "Eligible-topic ranking",
            html,
        )

        self.assertIn(
            "Selected recurring topic",
            html,
        )

        self.assertNotIn(
            "AGENDA EVOLUTION · 30 DAYS",
            html,
        )

        self.assertIn(
            '<h3 class="hybrid-section-title" data-fr27-type="module-title">Eligible-topic ranking</h3>',
            html,
        )
        self.assertIn(
            '<div class="hybrid-section-title" data-fr27-type="kicker">Selected recurring topic</div>',
            html,
        )
        self.assertIn('data-fr27-type="item-title"', html)
        self.assertIn('data-fr27-type="data"', html)
        self.assertIn('data-fr27-type="meta"', html)
        self.assertIn(
            'class="hybrid-supporting-link" data-fr27-type="action-label"',
            html,
        )
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


    def test_module_navigation_includes_routed_issues(self):
        self.assertIn(
            'tabId: "signal-issues-tab"',
            self.js,
        )
        self.assertIn(
            'label: "ISSUES"',
            self.js,
        )
        self.assertIn(
            'panelId: "signal-issues-panel"',
            self.js,
        )

        self.assertNotIn(
            "signal-poll-compare-tab",
            self.js,
        )
        self.assertNotIn(
            '"POLL COMPARE"',
            self.js,
        )

    def test_three_column_primary_layout_is_locked(self):
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
            ".slice(0, 20)",
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
            "function resolveSignalViewFromHash",
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
            "Active-field mention rate",
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


    def test_candidate_mention_rate_semantics_are_explicit(self):
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
            "Active-field mention rate",
            renderer,
        )
        self.assertIn(
            "mention rate among active-field-linked race records",
            renderer,
        )
        self.assertIn(
            "rates can overlap and need not total 100 percent",
            renderer,
        )
        self.assertNotIn(
            "active-field candidate-linked share",
            renderer,
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
            "number(item.latestShare) +",
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
            '${previousShareText}${previousShareText === "—" ? "" : "%"}',
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


    def test_candidate_coverage_consumes_active_projection_only(self):
        for contract in (
            "state.candidateSignals.metadata?.activeFieldVisibility",
            "const activePrimary = activeFieldVisibility?.primary || null;",
            "...activePrimary.main.map",
            "...activePrimary.secondary.map",
            "candidateCoverageAvailable,",
            "activeFieldVisibility,",
        ):
            self.assertIn(contract, self.js)
        model = self.js[
            self.js.index("function buildMediaViewModel()"):
            self.js.index("function buildAgendaViewModel()")
        ]
        self.assertNotIn("resolveCandidateVisibility(payload)", model)

    def test_active_projection_unavailable_is_scoped_without_raw_fallback(self):
        model = self.js[
            self.js.index("function buildMediaViewModel()"):
            self.js.index("function buildAgendaViewModel()")
        ]
        renderer = self.js[
            self.js.index("function renderTopMediaPulsePanel("):
            self.js.index("function renderTopMediaPulse(",
                          self.js.index("function renderTopMediaPulsePanel("))
        ]
        self.assertIn("candidateCoverageAvailable = Boolean(activePrimary)", model)
        self.assertIn("Active-field candidate comparison unavailable.", renderer)
        self.assertIn('tierLabel: row.tier.toUpperCase()', model)
        self.assertNotIn("candidatePeriods", model)
        self.assertNotIn("canonicalizeCandidate", model)

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

    def test_primary_active_rows_render_raw_period_differences(self):
        payload = json.loads(
            (ROOT / "candidate_signals.json").read_text(
                encoding="utf-8"
            )
        )
        primary = payload[
            "active_field_visibility"
        ]["primary"]

        quality = primary["comparison_quality"]
        rows = primary["main"] + primary["secondary"]
        self.assertTrue(rows)
        current_count = primary["current_period"]["record_count"]
        prior_count = primary["prior_period"]["record_count"]
        round_ratio = lambda value: int(value * 1000 + 0.5) / 1000
        for row in rows:
            expected_current = (
                round_ratio(row["current_record_count"] / current_count)
                if current_count
                else None
            )
            expected_prior = (
                round_ratio(row["prior_record_count"] / prior_count)
                if prior_count
                else None
            )
            self.assertEqual(row["current_share"], expected_current)
            self.assertEqual(row["prior_share"], expected_prior)
            if (
                quality["status"] == "comparable"
                and expected_current is not None
                and expected_prior is not None
            ):
                self.assertIsNotNone(row["share_change"])
            else:
                self.assertIsNone(row["share_change"])
        self.assertFalse(
            set(payload["presidential_field"]["hidden"])
            & {row["candidate_id"] for row in rows}
        )

        renderer = self.js[
            self.js.index(
                "function renderTopMediaPulsePanel("
            ):
            self.js.index(
                "function renderTopMediaPulse(",
                self.js.index(
                    "function renderTopMediaPulsePanel("
                ),
            )
        ]

        row_renderer = renderer[
            renderer.index("const shiftRows"):
            renderer.index("const maxTopicDays")
        ]

        presentation_start = self.js.index(
            "function topMediaComparisonPresentation("
        )
        sync_start = self.js.index(
            "function syncTopMediaShiftQualityLabel("
        )
        renderer_start = self.js.index(
            "function renderTopMediaPulsePanel("
        )

        presentation_source = self.js[
            presentation_start:sync_start
        ]
        sync_source = self.js[
            sync_start:renderer_start
        ]

        script = presentation_source + sync_source + r"""
const selector =
  ".top-media-shift .top-media-section-heading::after";
const contentRule = {
  selectorText: selector,
  style: { content: '"Δ pp"' }
};
const layoutRule = {
  selectorText: selector,
  style: { content: "" }
};
const document = {
  styleSheets: [
    { cssRules: [contentRule, layoutRule] }
  ]
};
const invalid = topMediaComparisonPresentation({
  candidateCoverageAvailable: true,
  comparisonQuality: {
    status: "not_comparable",
    reason: "publisher_panel_changed"
  }
});
const comparable = topMediaComparisonPresentation({
  candidateCoverageAvailable: true,
  comparisonQuality: {
    status: "comparable",
    reason: "comparable"
  }
});
const invalidUpdates =
  syncTopMediaShiftQualityLabel(invalid.label);
const invalidContent = contentRule.style.content;
const comparableUpdates =
  syncTopMediaShiftQualityLabel(comparable.label);
const comparableContent = contentRule.style.content;
process.stdout.write(JSON.stringify({
  invalid,
  comparable,
  invalidUpdates,
  invalidContent,
  comparableUpdates,
  comparableContent
}));
"""

        completed = subprocess.run(
            ["node", "-"],
            cwd=ROOT,
            input=script,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        presentation = json.loads(
            completed.stdout
        )

        raw_label = "RAW Δ pp"

        self.assertEqual(
            presentation["invalid"]["label"],
            raw_label,
        )
        self.assertIn(
            "Raw arithmetic current-minus-prior",
            presentation["invalid"]["explanation"],
        )
        self.assertIn(
            "reason: publisher_panel_changed",
            presentation["invalid"]["explanation"],
        )
        self.assertEqual(
            presentation["invalidUpdates"],
            1,
        )
        self.assertEqual(
            presentation["invalidContent"],
            f'"{raw_label}"',
        )
        self.assertEqual(
            presentation["comparable"]["label"],
            "Δ pp",
        )
        self.assertEqual(
            presentation["comparableUpdates"],
            1,
        )
        self.assertEqual(
            presentation["comparableContent"],
            '"Δ pp"',
        )

        self.assertEqual(
            self.html.count('content: "Δ pp";'),
            1,
        )
        self.assertIn(
            "const rawDeltaAvailable",
            row_renderer,
        )
        self.assertIn(
            "item.latestShare - item.previousShare",
            row_renderer,
        )
        self.assertIn(
            "raw arithmetic difference ${deltaText}",
            row_renderer,
        )
        self.assertIn(
            'direction + " " + escapeHtml(deltaText)',
            row_renderer,
        )
        self.assertIn(
            '"is-up"',
            row_renderer,
        )
        self.assertIn(
            '"is-down"',
            row_renderer,
        )
        self.assertNotIn(
            "isRawDelta",
            row_renderer,
        )
        self.assertNotIn(
            "Not comparable",
            row_renderer,
        )
        self.assertNotIn(
            "displayedDelta = deltaAvailable ? item.delta : 0",
            renderer,
        )
        self.assertIn(
            'class="hybrid-status-chip"',
            row_renderer,
        )

    def test_general_active_rows_suppress_unavailable_change(self):
        source_payload = json.loads(
            (ROOT / "candidate_signals.json").read_text(
                encoding="utf-8"
            )
        )
        payload = json.loads(json.dumps(source_payload))
        general = payload["active_field_visibility"]["general"]
        quality = general["comparison_quality"]
        thresholds = {
            "minimum_period_records": 10,
            "minimum_period_publishers": 5,
            "minimum_common_publishers": 5,
            "minimum_publisher_overlap_ratio": 0.5,
            "maximum_record_count_ratio": 2.0,
        }

        for period_name in ("current_period", "prior_period"):
            general[period_name]["record_count"] = 0
            general[period_name]["publisher_count"] = 0
        quality.update({
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
        })
        for tier in ("main", "secondary"):
            for row in general[tier]:
                row.update({
                    "current_record_count": 0,
                    "current_share": None,
                    "prior_record_count": 0,
                    "prior_share": None,
                    "share_change": None,
                })
            general[tier].sort(
                key=lambda row: (
                    row["candidate_name"].lower(),
                    row["candidate_id"],
                )
            )

        state = run_candidate_module(
            "api.normalize(input.payload)",
            payload,
        )
        self.assertEqual(state["status"], "ready")
        normalized_general = state["metadata"][
            "activeFieldVisibility"
        ]["general"]
        quality = normalized_general["comparison_quality"]

        self.assertEqual(quality["status"], "not_comparable")
        self.assertEqual(
            quality["reason"],
            "insufficient_data",
        )
        self.assertEqual(quality["thresholds"], thresholds)
        self.assertEqual(quality["publisher_overlap_ratio"], 0.0)
        self.assertIsNone(quality["record_count_ratio"])

        rows = normalized_general["main"] + normalized_general["secondary"]
        self.assertTrue(rows)
        self.assertTrue(
            all(row["share_change"] is None for row in rows)
        )


class BoundedTopRowPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = Path(
            "assets/final-dashboard-shell.css"
        ).read_text(encoding="utf-8")
        cls.javascript = Path(
            "assets/hybrid-dashboard.js"
        ).read_text(encoding="utf-8")

    def test_desktop_top_row_ratio_and_height(self):
        for contract in (
            "/* DESKTOP FOUNDATION STABILIZATION V1",
            "minmax(0, 28fr)",
            "minmax(0, 35fr)",
            "minmax(0, 37fr) !important;",
            "--fr27-desktop-hero-height: 400px;",
        ):
            self.assertIn(contract, self.css)

    def test_latest_coverage_renders_twenty_items(self):
        self.assertIn(
            "const coverageRows = model.feedItems",
            self.javascript,
        )
        self.assertIn(
            ".slice(0, 20)",
            self.javascript,
        )

    def test_latest_coverage_has_fixed_footer_and_scrollable_list(self):
        self.assertIn(
            "grid-template-rows:",
            self.css,
        )
        self.assertIn(
            "minmax(0, 1fr)",
            self.css,
        )
        self.assertIn(
            "overflow-y: auto;",
            self.css,
        )
        self.assertIn(
            "scrollbar-gutter: stable;",
            self.css,
        )

    def test_top_ctas_share_identical_typography(self):
        for contract in (
            "--top-row-cta-height: 32px;",
            "height: var(--top-row-cta-height);",
            "font-size: 9px !important;",
            "font-weight: 700 !important;",
            "line-height: 1 !important;",
        ):
            self.assertIn(contract, self.css)


class TopMediaProgressiveDisclosureTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.javascript = Path(
            "assets/hybrid-dashboard.js"
        ).read_text(encoding="utf-8")

        cls.css = Path(
            "assets/final-dashboard-shell.css"
        ).read_text(encoding="utf-8")

    def test_top_media_uses_two_accessible_tabs(self):
        for contract in (
            'role="tablist"',
            'data-top-media-tab="coverage"',
            'data-top-media-tab="overview"',
            'data-top-media-panel="coverage"',
            'data-top-media-panel="overview"',
            'aria-selected="true"',
            'aria-selected="false"',
        ):
            self.assertIn(
                contract,
                self.javascript,
            )

    def test_top_media_tabs_support_keyboard_navigation(self):
        for contract in (
            "function bindTopMediaTabs()",
            '"ArrowLeft"',
            '"ArrowRight"',
            '"Home"',
            '"End"',
            'activate("overview");',
            "bindTopMediaTabs();",
        ):
            self.assertIn(
                contract,
                self.javascript,
            )

    def test_top_media_panels_use_full_width(self):
        marker = (
            "/* TOP MEDIA PULSE PROGRESSIVE "
            "DISCLOSURE — 2026-07 */"
        )

        self.assertEqual(
            self.css.count(marker),
            1,
        )

        progressive_css = self.css.split(
            marker,
            1,
        )[1]

        for contract in (
            ".top-media-tabs",
            ".top-media-tab-panel[hidden]",
            "grid-template-columns:",
            "minmax(0, 1fr) !important;",
            "min-height: 74px;",
        ):
            self.assertIn(
                contract,
                progressive_css,
            )

    def test_race_title_and_six_row_geometry_are_preserved(self):
        marker = (
            "/* TOP MEDIA PULSE PROGRESSIVE "
            "DISCLOSURE — 2026-07 */"
        )

        progressive_css = self.css.split(
            marker,
            1,
        )[1]

        self.assertIn(
            "minmax(145px, .78fr)",
            progressive_css,
        )

        self.assertIn(
            "white-space: nowrap;",
            progressive_css,
        )

        self.assertIn(
            "min-height: 43px;",
            progressive_css,
        )

    def test_overview_is_first_and_default(self):
        overview_tab = self.javascript.index(
            'data-top-media-tab="overview"'
        )

        coverage_tab = self.javascript.index(
            'data-top-media-tab="coverage"'
        )

        self.assertLess(
            overview_tab,
            coverage_tab,
        )

        self.assertIn(
            'activate("overview");',
            self.javascript,
        )

        self.assertIn(
            'panel.style.display =',
            self.javascript,
        )

        marker = (
            "/* TOP MEDIA TAB STATE HARDENING "
            "— OVERVIEW DEFAULT — 2026-07 */"
        )

        self.assertEqual(
            self.css.count(marker),
            1,
        )

        hardened_css = self.css.split(
            marker,
            1,
        )[1]

        self.assertIn(
            "> .top-media-tab-panel[hidden]",
            hardened_css,
        )

        self.assertIn(
            "display: none !important;",
            hardened_css,
        )

        self.assertIn(
            "> .top-media-tabs",
            hardened_css,
        )

        self.assertIn(
            "display: flex !important;",
            hardened_css,
        )

class MockupTopRowGeometryTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.javascript = Path(
            "assets/hybrid-dashboard.js"
        ).read_text(encoding="utf-8")

        cls.css = Path(
            "assets/final-dashboard-shell.css"
        ).read_text(encoding="utf-8")

    def test_final_panel_proportions_match_reference(self):
        marker = (
            "/* MOCKUP TOP-ROW GEOMETRY AND "
            "COVERAGE SHIFT CARD — 2026-07 */"
        )

        self.assertEqual(
            self.css.count(marker),
            1,
        )

        final_css = self.css.split(
            marker,
            1,
        )[1]

        for contract in (
            "minmax(0, 28fr)",
            "minmax(0, 35fr)",
            "minmax(0, 37fr)",
        ):
            self.assertIn(
                contract,
                final_css,
            )

    def test_overview_matches_coverage_shift_card_anatomy(self):

        self.assertNotIn(
            "top-media-shift-subtitle",
            self.javascript,
        )

        self.assertIn(
            "MEDIA OVERVIEW SUBTITLE REMOVAL "
            "AND HEIGHT TRANSFER",
            self.css,
        )

        marker = (
            "/* MOCKUP TOP-ROW GEOMETRY AND "
            "COVERAGE SHIFT CARD — 2026-07 */"
        )

        final_css = self.css.split(
            marker,
            1,
        )[1]

        for contract in (
            ".top-media-shift-subtitle",
            "minmax(112px, 178px)",
            "repeat(",
            "112px",
            "grid-template-columns:",
        ):
            self.assertIn(
                contract,
                final_css,
            )


class DesktopFoundationStabilizationTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.index = Path(
            "index.html"
        ).read_text(encoding="utf-8")
        cls.css = Path(
            "assets/final-dashboard-shell.css"
        ).read_text(encoding="utf-8")
        cls.javascript = Path(
            "assets/hybrid-dashboard.js"
        ).read_text(encoding="utf-8")

        marker = (
            "/* DESKTOP FOUNDATION "
            "STABILIZATION V1"
        )
        cls.stabilized_css = cls.css.split(
            marker,
            1,
        )[1]

    def test_runtime_tabs_use_five_equal_tracks(self):
        tab_rule = re.search(
            r"#hybrid-signal-board \.hybrid-tabs \{"
            r"(?P<body>.*?)\}",
            self.css,
            re.DOTALL,
        )

        self.assertIsNotNone(tab_rule)
        self.assertIn(
            "repeat(5, minmax(0, 1fr))",
            tab_rule.group("body"),
        )
        self.assertNotIn(
            "repeat(6, minmax(0, 1fr))",
            tab_rule.group("body"),
        )

        self.assertIn(
            "repeat(5, minmax(0, 1fr));",
            self.index,
        )

        for panel_id in (
            "signal-candidates-panel",
            "signal-runoff-panel",
            "signal-events-panel",
            "signal-agenda-panel",
            "signal-issues-panel",
        ):
            self.assertIn(panel_id, self.javascript)

        self.assertNotIn(
            "signal-poll-compare-panel",
            self.javascript,
        )

    def test_desktop_composition_is_reasserted_once(self):
        for contract in (
            "@media (min-width: 1024px)",
            "minmax(0, 28fr)",
            "minmax(0, 35fr)",
            "minmax(0, 37fr) !important;",
            "grid-column: auto !important;",
            "repeat(5, minmax(0, 1fr));",
            "flex-wrap: nowrap;",
            "--fr27-desktop-hero-height: 400px;",
            "--fr27-desktop-context-height: 66px;",
            "--fr27-desktop-tab-height: 44px;",
            "--fr27-desktop-panel-height: 462px;",
        ):
            self.assertIn(
                contract,
                self.stabilized_css,
            )

        self.assertEqual(
            self.css.count("minmax(0, 28fr)"),
            1,
        )

        for obsolete_columns in (
            "minmax(0, 27fr)",
            "minmax(0, 30fr)",
            "minmax(0, 32fr)",
            "minmax(0, 41fr)",
            "minmax(0, 43fr)",
        ):
            self.assertNotIn(
                obsolete_columns,
                self.css,
            )

        self.assertNotRegex(
            self.index,
            r"@media \(max-width: 1350px\) \{\s*"
            r"\.hero-grid",
        )

    def test_desktop_hero_gap_stays_compact(self):
        hero_rule = re.search(
            r"\.hero-grid \{(?P<body>.*?)\}",
            self.css,
            re.DOTALL,
        )

        self.assertIsNotNone(hero_rule)
        self.assertIn(
            "margin-top: 6px;",
            hero_rule.group("body"),
        )
        self.assertNotIn(
            "margin-top: 10px;",
            hero_rule.group("body"),
        )

    def test_compact_desktop_uses_shared_density_tokens(self):
        compact_start = self.stabilized_css.index(
            "@media (min-width: 1240px) "
            "and (max-width: 1399px)"
        )
        narrow_start = self.stabilized_css.index(
            "@media (min-width: 1024px) "
            "and (max-width: 1239px)",
            compact_start,
        )
        compact_tokens = self.stabilized_css[
            compact_start:narrow_start
        ]

        for contract in (
            "--fr27-desktop-shell-inline-padding: 16px;",
            "--fr27-desktop-mark-size: 46px;",
            "--fr27-desktop-masthead-title-size: 22px;",
            "--fr27-desktop-panel-title-size: 14px;",
            "--fr27-desktop-reading-size: 11.5px;",
            "--fr27-desktop-action-size: 10px;",
            "--fr27-desktop-filter-gap: 3px;",
            "--fr27-desktop-filter-inline-padding: 6px;",
        ):
            self.assertIn(
                contract,
                compact_tokens,
            )

        self.assertNotIn(
            "transform: scale",
            self.stabilized_css,
        )
        self.assertNotRegex(
            self.stabilized_css,
            r"(?:^|\s)zoom\s*:",
        )

        desktop_start = self.stabilized_css.index(
            "@media (min-width: 1024px) {",
            narrow_start,
        )
        narrow_tokens = self.stabilized_css[
            narrow_start:desktop_start
        ]
        for contract in (
            "--fr27-desktop-shell-inline-padding: 12px;",
            "--fr27-desktop-masthead-title-size: 18px;",
            "--fr27-desktop-reading-size: 10.5px;",
            "--fr27-workspace-gap: 6px;",
            "--fr27-workspace-portrait-size: 34px;",
        ):
            self.assertIn(contract, narrow_tokens)

    def test_compact_top_row_controls_stay_in_their_panel(self):
        for contract in (
            ".changes-ledger-toolbar {",
            "width: 100%;",
            "min-width: 0;",
            "max-width: 100%;",
            "gap: var(--fr27-desktop-filter-gap);",
            "padding-right: var("
            "--fr27-desktop-filter-inline-padding);",
            "padding-left: var("
            "--fr27-desktop-filter-inline-padding);",
        ):
            self.assertIn(
                contract,
                self.stabilized_css,
        )


class DesktopWorkspaceStabilizationTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.shell_css = Path(
            "assets/final-dashboard-shell.css"
        ).read_text(encoding="utf-8")
        cls.hybrid_css = Path(
            "assets/hybrid-dashboard.css"
        ).read_text(encoding="utf-8")
        cls.candidate_css = Path(
            "assets/candidate-signals.css"
        ).read_text(encoding="utf-8")

        cls.workspace_css = cls.hybrid_css.split(
            "/* DESKTOP WORKSPACE "
            "STABILIZATION PASS 2",
            1,
        )[1]
        cls.shared_workspace_css = cls.hybrid_css.split(
            "/* SHARED DESKTOP WORKSPACE "
            "DENSITY PASS 2",
            1,
        )[1].split(
            "/* RUNOFF WORKSPACE REDESIGN V1",
            1,
        )[0]
        cls.candidate_workspace_css = (
            cls.candidate_css.split(
                "/* DESKTOP WORKSPACE "
                "STABILIZATION PASS 2",
                1,
            )[1]
        )

    def test_shared_workspace_density_tokens_have_three_desktop_values(self):
        for wide, compact, narrow in (
            (
                "--fr27-workspace-gap: 10px;",
                "--fr27-workspace-gap: 8px;",
                "--fr27-workspace-gap: 6px;",
            ),
            (
                "--fr27-workspace-inline-padding: 10px;",
                "--fr27-workspace-inline-padding: 8px;",
                "--fr27-workspace-inline-padding: 6px;",
            ),
            (
                "--fr27-workspace-panel-title-size: 13px;",
                "--fr27-workspace-panel-title-size: 12px;",
                "--fr27-workspace-panel-title-size: 11px;",
            ),
            (
                "--fr27-workspace-primary-size: 12.5px;",
                "--fr27-workspace-primary-size: 11.5px;",
                "--fr27-workspace-primary-size: 10.5px;",
            ),
            (
                "--fr27-workspace-portrait-size: 46px;",
                "--fr27-workspace-portrait-size: 40px;",
                "--fr27-workspace-portrait-size: 34px;",
            ),
        ):
            with self.subTest(token=wide.split(":", 1)[0]):
                self.assertIn(wide, self.shell_css)
                self.assertIn(compact, self.shell_css)
                self.assertIn(narrow, self.shell_css)

        self.assertIn(
            "@media (min-width: 1240px) "
            "and (max-width: 1399px)",
            self.shell_css,
        )
        self.assertIn(
            "@media (min-width: 1024px) "
            "and (max-width: 1239px)",
            self.shell_css,
        )

    def test_all_active_workspace_panels_keep_the_462px_contract(self):
        for contract in (
            "--fr27-desktop-panel-height: 462px;",
            "height: var(--fr27-desktop-panel-height);",
            "min-height: var(--fr27-desktop-panel-height);",
            "max-height: var(--fr27-desktop-panel-height);",
        ):
            self.assertIn(contract, self.shell_css)

        for panel_id in (
            "signal-candidates-panel",
            "signal-runoff-panel",
            "signal-events-panel",
            "signal-agenda-panel",
            "signal-issues-panel",
        ):
            self.assertIn(panel_id, self.hybrid_css)

    def test_candidates_compact_desktop_keeps_three_columns(self):
        desktop = self.candidate_css[
            self.candidate_css.index(
                "@media (min-width: 1024px)"
            ):
            self.candidate_css.index(
                "/* Legacy tablet layout only."
            )
        ]

        for column in (
            "minmax(0, 27fr)",
            "minmax(0, 36fr)",
            "minmax(0, 37fr)",
        ):
            self.assertIn(column, desktop)

        self.assertIn(
            "@media (min-width: 760px) "
            "and (max-width: 1023px)",
            self.candidate_css,
        )
        self.assertIn(
            "gap: var(--fr27-workspace-gap);",
            self.candidate_workspace_css,
        )
        self.assertNotIn(
            "position: sticky;",
            self.candidate_workspace_css,
        )
        self.assertNotIn(
            "grid-column: 1 / -1;",
            self.candidate_workspace_css,
        )

    def test_runoff_compact_tracks_cannot_impose_right_edge_overflow(self):
        for contract in (
            "minmax(0, 31.5fr)",
            "minmax(0, 39fr)",
            "minmax(0, 29.5fr)",
            "minmax(88px, 1fr)",
            "minmax(98px, 1.12fr)",
            "minmax(112px, 1.28fr)",
            "minmax(78px, 1fr)",
            "width: 50px;",
            "min-width: 50px;",
            "minmax(0, 30.5fr)",
            "minmax(0, 40fr)",
            "minmax(76px, 1fr)",
            "minmax(70px, 1.1fr)",
            "width: calc(100% - 2px);",
        ):
            self.assertIn(contract, self.workspace_css)

        for contract in (
            "width: 100%;",
            "min-width: 0;",
            "max-width: 88px;",
        ):
            self.assertIn(
                contract,
                self.hybrid_css.split(
                    "/* Runoff structural containment.",
                    1,
                )[1].split(
                    "/* DESKTOP WORKSPACE "
                    "STABILIZATION PASS 2",
                    1,
                )[0],
            )

        self.assertNotIn(
            "grid-column: 1 / -1;",
            self.workspace_css,
        )

    def test_events_compact_desktop_keeps_timeline_and_three_peer_panels(self):
        events = self.hybrid_css[
            self.hybrid_css.index(
                "/* CAMPAIGN EVENTS WORKSPACE V1 */"
            ):
            self.hybrid_css.index(
                "/* RUNOFF WORKSPACE REDESIGN V1"
            )
        ]

        self.assertIn(
            "grid-template-rows: 96px minmax(0, 1fr) 22px;",
            events,
        )
        self.assertIn(
            "grid-template-columns: minmax(0, 31fr) "
            "minmax(0, 34.5fr) minmax(0, 34.5fr);",
            events,
        )
        self.assertNotIn(
            "@media (max-width: 1260px)",
            self.hybrid_css,
        )
        self.assertIn(
            "@media (max-width: 1023px)",
            events,
        )
        self.assertIn(
            ".hybrid-events-ops-main",
            self.shared_workspace_css,
        )

    def test_agenda_and_issues_keep_the_canonical_three_column_graph(self):
        agenda = self.hybrid_css[
            self.hybrid_css.index(
                "/* AGENDA WORKSPACE"
            ):
            self.hybrid_css.index(
                "/* CAMPAIGN EVENTS WORKSPACE V1 */"
            )
        ]

        self.assertIn(
            "grid-template-columns: minmax(0, 27fr) "
            "minmax(0, 36fr) minmax(0, 37fr);",
            agenda,
        )
        self.assertIn(
            "@media (max-width: 1023px)",
            agenda,
        )
        self.assertIn(
            ":is(#signal-agenda-panel, "
            "#signal-issues-panel)",
            self.shared_workspace_css,
        )
        self.assertNotIn(
            "grid-template-columns: 1fr;",
            self.shared_workspace_css,
        )

    def test_issue_evolution_matrix_can_shrink_and_scroll_vertically(self):
        matrix_rules = re.findall(
            r"\.hybrid-panel#signal-issues-panel\s+"
            r"\.hybrid-agenda-v6-matrix\s*\{"
            r"(?P<body>.*?)\}",
            self.hybrid_css,
            re.DOTALL,
        )

        self.assertTrue(
            any(
                "min-width: 0" in body
                and "min-height: 0" in body
                and "overflow-x: hidden" in body
                and "overflow-y: auto" in body
                for body in matrix_rules
            )
        )

    def test_final_desktop_floor_and_legacy_boundary_are_complementary(self):
        self.assertIn("@media (min-width: 1024px) {", self.shell_css)
        self.assertIn(
            "@media (min-width: 1024px) {",
            self.candidate_css,
        )
        self.assertIn(
            "@media (min-width: 1024px) {",
            self.hybrid_css,
        )

        shell_desktop = self.shell_css.split(
            "/* DESKTOP FOUNDATION STABILIZATION V1",
            1,
        )[1]
        for contract in (
            "grid-template-columns:\n      minmax(0, 28fr)",
            "grid-template-columns:\n      minmax(0, 1.06fr)",
            "repeat(5, minmax(0, 1fr))",
            "height: var(--fr27-desktop-panel-height);",
        ):
            self.assertIn(contract, shell_desktop)

        runoff = self.hybrid_css.split(
            "/* RUNOFF WORKSPACE REDESIGN V1",
            1,
        )[1]
        for obsolete in (
            "max-width: 1179px",
            "min-width: 1180px",
            "max-width: 1180px",
            "max-width: 1250px",
            "min-width: 1251px",
            "min-width: 1100px",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, runoff)

        self.assertIn("max-width: 1023px", runoff)
        self.assertIn("min-width: 1024px", runoff)
        self.assertIn("min-width: 1400px", runoff)

    def test_no_desktop_density_regime_scales_the_page(self):
        desktop_css = "\n".join(
            (self.shell_css, self.hybrid_css, self.candidate_css)
        )
        self.assertNotIn("transform: scale(", desktop_css)
        self.assertNotRegex(desktop_css, r"(?:^|[;{])\s*zoom\s*:")



class HeroBrandingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = Path(
            "index.html"
        ).read_text(encoding="utf-8")
        cls.css = Path(
            "assets/final-dashboard-shell.css"
        ).read_text(encoding="utf-8")

    def test_locked_hero_branding_contract(self):
        self.assertIn(
            '<h1 data-fr27-type="display">FRANCE 2027 <span>SIGNAL LAB</span></h1>',
            self.index,
        )
        self.assertNotIn(
            'style="color:var(--blue)">SIGNAL LAB',
            self.index,
        )

        for contract in (
            "font-size: clamp(22px, 1.5vw, 26px);",
            "font-weight: 600;",
            "letter-spacing: 0.065em;",
            ".masthead h1::after",
            "#0055a4 0 33.333%",
            "#ffffff 33.333% 66.666%",
            "#ef4135 66.666% 100%",
            "@media (min-width: 720px) and (max-width: 1023px)",
            ".masthead-data span",
            "white-space: normal;",
        ):
            self.assertIn(
                contract,
                self.css,
            )

        self.assertIn(
            """.mark svg {
      width: 42px;
      height: 42px;""",
            self.index,
        )


if __name__ == "__main__":
    unittest.main()
