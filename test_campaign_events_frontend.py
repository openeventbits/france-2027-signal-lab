import copy
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
DASHBOARD = ROOT / "assets" / "hybrid-dashboard.js"
CSS = ROOT / "assets" / "hybrid-dashboard.css"
ARTIFACT = ROOT / "campaign_events.json"


def run_node_json(script, payload):
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("Node.js is required for frontend behavior tests")
    completed = subprocess.run(
        [node, "-e", script],
        cwd=ROOT,
        input=json.dumps(payload),
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def validate_frontend_payload(payload):
    script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("index.html", "utf8").replace(/\r\n?/g, "\n");
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const extract = (startMarker, endMarker) => {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  if (start < 0 || end < 0) throw new Error(`Could not extract ${startMarker}`);
  return source.slice(start, end);
};
const context = { URL, Date, Intl, Set, Number };
vm.runInNewContext([
  extract("    function safeSourceUrl(", "\n\n    const dashboardState"),
  extract(
    "    function validateCampaignEventsPayload(",
    "\n\n    function loadCampaignEvents("
  )
].join("\n"), context);
try {
  context.validateCampaignEventsPayload(payload);
  process.stdout.write(JSON.stringify({ valid: true, error: null }));
} catch (error) {
  process.stdout.write(JSON.stringify({ valid: false, error: error.message }));
}
'''
    return run_node_json(script, payload)


def build_events_view_model(payload, state, now=None):
    script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("assets/hybrid-dashboard.js", "utf8")
  .replace(/\r\n?/g, "\n");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const RealDate = Date;
class FixedDate extends RealDate {
  constructor(...args) {
    super(...(args.length ? args : [input.now || RealDate.now()]));
  }
  static now() {
    return input.now
      ? new RealDate(input.now).getTime()
      : RealDate.now();
  }
}
const start = source.indexOf("  function parisTodayKey(");
const end = source.indexOf("\n\n  function safelyBuildViewModel(", start);
if (start < 0 || end < 0) throw new Error("Could not extract Events view model");
const context = {
  Date: FixedDate,
  Intl,
  Map,
  Set,
  Number,
  dashboardState: {
    campaignEvents: input.payload,
    loadState: { campaignEvents: "loaded" }
  },
  state: input.state,
  viewModelState() { return null; },
  utcDateKey(date) { return date.toISOString().slice(0, 10); },
  campaignEventMatchesTypeFilter(event, filterKey) {
    return !filterKey || filterKey === "all" || event.event_type === filterKey;
  }
};
vm.runInNewContext(source.slice(start, end), context);
const model = context.buildEventsViewModel();
process.stdout.write(JSON.stringify({
  state: input.state,
  model: {
    state: model.state,
    eventTypeFilter: model.eventTypeFilter,
    selectedEventId: model.selectedEvent?.event_id || null,
    upcomingIds: model.upcomingEvents.map(event => event.event_id),
    filteredUpcomingIds: model.filteredUpcomingEvents.map(event => event.event_id),
    pastScheduledIds: model.pastScheduledEvents.map(event => event.event_id),
    inactiveIds: model.inactiveEvents.map(event => event.event_id),
    nonActiveIds: model.nonActiveEvents.map(event => event.event_id),
    horizonIds: model.horizon.events.map(event => event.event_id),
    upcomingCount: model.upcomingCount,
    pastCount: model.pastCount,
    inactiveCount: model.inactiveCount,
    next14Count: model.next14Count,
    multiCandidateCount: model.multiCandidateCount,
    verifiedCount: model.verifiedCount
  },
  invalidDateAccepted: Boolean(context.campaignEventDateFromKey("2099-02-30"))
}));
'''
    return run_node_json(script, {"payload": payload, "state": state, "now": now})




def campaign_event_date_only_display_label(value, timezone):
    script = r'''
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
process.env.TZ = input.timezone;

const source = fs.readFileSync("assets/hybrid-dashboard.js", "utf8")
  .replace(/\r\n?/g, "\n");

const start = source.indexOf("  function campaignEventDateFromKey(");
const end = source.indexOf(
  "\n\n  function campaignEventMonthLong(",
  start
);

if (start < 0 || end < 0) {
  throw new Error("Could not extract Campaign Events date-only helpers");
}

const context = { Date };
vm.runInNewContext(source.slice(start, end), context);

const date = context.campaignEventDateFromKey(input.value);
if (!date) {
  throw new Error("Date-only fixture was rejected");
}

process.stdout.write(JSON.stringify({
  label: `${date.getUTCDate()} ${context.campaignEventMonthShort(input.value)}`
}));
'''
    return run_node_json(
        script,
        {"value": value, "timezone": timezone},
    )["label"]

class CampaignEventsFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = INDEX.read_text(encoding="utf-8")
        cls.dashboard = DASHBOARD.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")
        cls.artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_public_artifact_has_frontend_lanes(self):
        self.assertEqual(self.artifact["schema_version"], "1.1")
        self.assertIsInstance(self.artifact["campaign_events"], list)
        self.assertIsInstance(self.artifact["institutional_milestones"], list)
        self.assertIsInstance(self.artifact["event_watch"], list)

    def test_event_watch_references_campaign_events(self):
        event_ids = {
            event["event_id"]
            for event in self.artifact["campaign_events"]
        }
        self.assertTrue(event_ids)
        for update in self.artifact["event_watch"]:
            self.assertIn(update["event_id"], event_ids)

    def test_campaign_events_uses_central_dashboard_state(self):
        self.assertIn("campaignEvents: null", self.index)
        self.assertIn('campaignEvents: "loading"', self.index)
        self.assertIn(
            'markDataset(\n            "campaignEvents",\n            "loaded"',
            self.index,
        )
        self.assertIn('markDataset("campaignEvents", "error")', self.index)

    def test_public_artifact_is_fetched_once_outside_hybrid_renderer(self):
        needle = 'fetch("campaign_events.json", { cache: "no-store" })'
        self.assertEqual(self.index.count(needle), 1)
        self.assertNotIn('fetch("campaign_events.json"', self.dashboard)
        self.assertIn("loadCampaignEvents();", self.index)

    def test_frontend_validator_preserves_locked_public_contract(self):
        validator_start = self.index.index(
            "function validateCampaignEventsPayload("
        )
        loader_start = self.index.index(
            "function loadCampaignEvents(",
            validator_start,
        )
        validator = self.index[validator_start:loader_start]
        for value in (
            '"1.1"',
            '"scheduled"',
            '"postponed"',
            '"cancelled"',
            '"completed"',
            '"NEW"',
            '"CONFIRMED"',
            '"UPDATED"',
            '"POSTPONED"',
            '"CANCELLED"',
            "institutional_milestones",
            "event_watch",
        ):
            with self.subTest(value=value):
                self.assertIn(value, validator)

    def test_frontend_validator_accepts_current_public_artifact(self):
        result = validate_frontend_payload(self.artifact)
        self.assertTrue(result["valid"], result["error"])

    def test_frontend_validator_rejects_runtime_unsafe_contract_defects(self):
        mutations = {}

        generated_millis = copy.deepcopy(self.artifact)
        generated_millis["generated_at"] = "2026-08-12T17:01:29.000Z"
        mutations["noncanonical generated_at"] = generated_millis

        invalid_date = copy.deepcopy(self.artifact)
        invalid_date["campaign_events"][0]["scheduled_start"] = "2099-02-30"
        invalid_date["campaign_events"][0]["time_precision"] = "date"
        mutations["impossible calendar date"] = invalid_date

        wrong_precision = copy.deepcopy(self.artifact)
        wrong_precision["campaign_events"][0]["time_precision"] = "date"
        mutations["precision mismatch"] = wrong_precision

        wrong_paris_offset = copy.deepcopy(self.artifact)
        wrong_paris_offset["campaign_events"][0]["scheduled_start"] = (
            "2026-08-23T10:00:00+01:00"
        )
        mutations["invalid Paris offset"] = wrong_paris_offset

        parallel_candidates = copy.deepcopy(self.artifact)
        parallel_candidates["campaign_events"][0]["candidate_ids"] = []
        mutations["nonparallel candidates"] = parallel_candidates

        unknown_evidence_status = copy.deepcopy(self.artifact)
        unknown_evidence_status["campaign_events"][0]["evidence_status"] = "likely"
        mutations["unknown evidence status"] = unknown_evidence_status

        unsafe_source = copy.deepcopy(self.artifact)
        unsafe_source["campaign_events"][0]["evidence"][0]["source_url"] = (
            "https://example.com/source#fragment"
        )
        mutations["unsafe source URL"] = unsafe_source

        bad_observed_at = copy.deepcopy(self.artifact)
        bad_observed_at["event_watch"][0]["observed_at"] = "2026-08-12"
        mutations["noncanonical watch timestamp"] = bad_observed_at

        future_data_as_of = copy.deepcopy(self.artifact)
        future_data_as_of["data_as_of"] = "2099-01-01T00:00:00Z"
        mutations["data_as_of after generated_at"] = future_data_as_of

        future_verification = copy.deepcopy(self.artifact)
        future_verification["campaign_events"][0]["last_verified_at"] = (
            "2099-01-01T00:00:00Z"
        )
        mutations["verification after generated_at"] = future_verification

        future_observation = copy.deepcopy(self.artifact)
        future_observation["event_watch"][0]["observed_at"] = (
            "2099-01-01T00:00:00Z"
        )
        mutations["observation after generated_at"] = future_observation

        invalid_past_status = copy.deepcopy(self.artifact)
        invalid_past_status["campaign_events"][0]["evidence_status"] = (
            "past_unconfirmed"
        )
        invalid_past_status["campaign_events"][0]["status"] = "postponed"
        mutations["past_unconfirmed non-scheduled"] = invalid_past_status

        invalid_past_timing = copy.deepcopy(self.artifact)
        timing_event = invalid_past_timing["campaign_events"][0]
        timing_event["status"] = "scheduled"
        timing_event["evidence_status"] = "past_unconfirmed"
        timing_event["scheduled_start"] = "2099-08-23"
        timing_event["time_precision"] = "date"
        timing_event.pop("scheduled_end", None)
        mutations["past_unconfirmed schedule not past"] = invalid_past_timing

        for label, payload in mutations.items():
            with self.subTest(label=label):
                result = validate_frontend_payload(payload)
                self.assertFalse(result["valid"], result)

        valid_past_unconfirmed = copy.deepcopy(self.artifact)
        valid_past_event = valid_past_unconfirmed["campaign_events"][0]
        valid_past_event["status"] = "scheduled"
        valid_past_event["evidence_status"] = "past_unconfirmed"
        valid_past_event["scheduled_start"] = "2000-01-01"
        valid_past_event["time_precision"] = "date"
        valid_past_event["last_verified_at"] = valid_past_unconfirmed["generated_at"]
        valid_past_event.pop("scheduled_end", None)
        valid_result = validate_frontend_payload(valid_past_unconfirmed)
        self.assertTrue(valid_result["valid"], valid_result["error"])

    def test_events_view_model_sort_and_selection_are_refresh_safe(self):
        def event(event_id, scheduled_start, *, event_type="rally", precision="datetime"):
            return {
                "event_key": event_id,
                "event_id": event_id,
                "event_type": event_type,
                "title": event_id,
                "candidate_ids": [],
                "candidate_names": [],
                "scheduled_start": scheduled_start,
                "time_precision": precision,
                "status": "scheduled",
            }

        events = [
            event("date-only", "2099-08-23", precision="date"),
            event("later-time", "2099-08-23T10:00:00+02:00"),
            event("earlier-time", "2099-08-23T09:00:00+02:00", event_type="debate"),
            event("past", "2000-01-01", precision="date"),
        ]
        payload = {
            "generated_at": "2026-08-12T17:01:29Z",
            "data_as_of": "2026-08-12T17:01:26Z",
            "campaign_events": events,
            "institutional_milestones": [],
            "event_watch": [],
        }

        first = build_events_view_model(
            payload,
            {
                "selectedCampaignEventId": "past",
                "selectedCampaignEventWeekStart": "",
                "campaignEventTypeFilter": "all",
            },
        )
        reversed_result = build_events_view_model(
            {**payload, "campaign_events": list(reversed(events))},
            {
                "selectedCampaignEventId": "past",
                "selectedCampaignEventWeekStart": "",
                "campaignEventTypeFilter": "all",
            },
        )

        expected = ["earlier-time", "later-time", "date-only"]
        self.assertEqual(first["model"]["upcomingIds"], expected)
        self.assertEqual(reversed_result["model"]["upcomingIds"], expected)
        self.assertEqual(first["model"]["selectedEventId"], "past")
        self.assertFalse(first["invalidDateAccepted"])

        filtered = build_events_view_model(
            payload,
            {
                "selectedCampaignEventId": "later-time",
                "selectedCampaignEventWeekStart": "",
                "campaignEventTypeFilter": "debate",
            },
        )
        self.assertEqual(filtered["model"]["selectedEventId"], "earlier-time")

        stale_filter = build_events_view_model(
            payload,
            {
                "selectedCampaignEventId": "later-time",
                "selectedCampaignEventWeekStart": "",
                "campaignEventTypeFilter": "visit",
            },
        )
        self.assertEqual(stale_filter["model"]["eventTypeFilter"], "all")
        self.assertEqual(stale_filter["state"]["campaignEventTypeFilter"], "all")

        emptied = build_events_view_model(
            {**payload, "campaign_events": []},
            {
                "selectedCampaignEventId": "later-time",
                "selectedCampaignEventWeekStart": "2099-08-17",
                "campaignEventTypeFilter": "all",
            },
        )
        self.assertIsNone(emptied["model"]["selectedEventId"])
        self.assertEqual(emptied["state"]["selectedCampaignEventId"], "")

    def test_events_view_model_enforces_active_schedule_lifecycle_matrix(self):
        def event(
            event_id,
            scheduled_start,
            *,
            status="scheduled",
            event_type="rally",
            candidate_names=None,
        ):
            names = list(candidate_names or [])
            return {
                "event_key": event_id,
                "event_id": event_id,
                "event_type": event_type,
                "title": event_id,
                "candidate_ids": [
                    f"candidate-{index}"
                    for index in range(len(names))
                ],
                "candidate_names": names,
                "scheduled_start": scheduled_start,
                "time_precision": "date",
                "status": status,
                "evidence_status": "verified",
            }

        events = [
            event(
                "future-scheduled",
                "2026-08-14",
                status="scheduled",
                event_type="debate",
            ),
            event(
                "future-postponed",
                "2026-08-15",
                status="postponed",
                event_type="rally",
                candidate_names=["Alpha", "Beta"],
            ),
            event(
                "future-cancelled",
                "2026-08-16",
                status="cancelled",
            ),
            event(
                "future-completed",
                "2026-08-17",
                status="completed",
            ),
            event(
                "past-scheduled",
                "2026-08-12",
                status="scheduled",
            ),
        ]

        payload = {
            "generated_at": "2026-08-13T10:00:00Z",
            "data_as_of": "2026-08-13T09:59:00Z",
            "campaign_events": events,
            "institutional_milestones": [],
            "event_watch": [],
        }

        result = build_events_view_model(
            payload,
            {
                "selectedCampaignEventId": "future-postponed",
                "selectedCampaignEventWeekStart": "",
                "campaignEventTypeFilter": "rally",
            },
            now="2026-08-13T10:00:00Z",
        )

        model = result["model"]

        self.assertEqual(
            model["upcomingIds"],
            ["future-scheduled"],
        )
        self.assertEqual(
            model["filteredUpcomingIds"],
            ["future-scheduled"],
        )
        self.assertEqual(
            model["horizonIds"],
            ["future-scheduled"],
        )
        self.assertEqual(
            model["pastScheduledIds"],
            ["past-scheduled"],
        )
        self.assertEqual(
            set(model["inactiveIds"]),
            {
                "future-postponed",
                "future-cancelled",
                "future-completed",
            },
        )
        self.assertEqual(
            set(model["nonActiveIds"]),
            {
                "future-postponed",
                "future-cancelled",
                "future-completed",
                "past-scheduled",
            },
        )

        self.assertEqual(model["upcomingCount"], 1)
        self.assertEqual(model["pastCount"], 1)
        self.assertEqual(model["inactiveCount"], 3)
        self.assertEqual(model["next14Count"], 1)
        self.assertEqual(model["multiCandidateCount"], 0)
        self.assertEqual(model["verifiedCount"], 1)

        # The inactive rally cannot keep the active schedule filtered to rally.
        self.assertEqual(model["eventTypeFilter"], "all")
        self.assertEqual(
            result["state"]["campaignEventTypeFilter"],
            "all",
        )

        # But a valid inactive dossier selection may survive refresh.
        self.assertEqual(
            model["selectedEventId"],
            "future-postponed",
        )

    def test_date_only_display_is_machine_timezone_independent(self):
        labels = [
            campaign_event_date_only_display_label(
                "2027-04-18",
                "America/Los_Angeles",
            ),
            campaign_event_date_only_display_label(
                "2027-04-18",
                "Pacific/Kiritimati",
            ),
        ]

        self.assertEqual(labels, ["18 APR", "18 APR"])
    def test_events_view_model_and_temporal_ops_desk_are_wired(self):
        self.assertIn("function buildEventsViewModel()", self.dashboard)
        self.assertIn(
            'viewModelState("campaignEvents")',
            self.dashboard,
        )
        self.assertIn(
            'events: safelyBuildViewModel("events", buildEventsViewModel)',
            self.dashboard,
        )
        self.assertIn(
            "${renderEventsPanel(models.events)}",
            self.dashboard,
        )
        for heading in (
            "Campaign Events temporal operations desk",
            "12-WEEK SCHEDULE",
            "UPCOMING EVENTS",
            "EVENT DOSSIER",
            "SOURCE EVIDENCE",
            "SCHEDULE HISTORY",
            "SCHEDULE WATCH",
            "MATERIAL CHANGES",
            "RECENT ADDITIONS",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.dashboard)

        self.assertIn("campaignEventTypeFilter", self.dashboard)
        self.assertIn('button[data-hybrid-event-id]', self.dashboard)
        self.assertIn('button[data-hybrid-week-select]', self.dashboard)
        self.assertIn('button[data-hybrid-events-filter]', self.dashboard)
        self.assertIn("selectedUpdates", self.dashboard)
        self.assertIn("eventWatch", self.dashboard)
        self.assertIn("hybrid-events-upcoming-row", self.dashboard)
        self.assertIn("hybrid-events-upcoming-week", self.dashboard)
        self.assertIn("hybrid-events-ops-marker", self.dashboard)
        self.assertIn("campaignEventHorizonCategoryLabel", self.dashboard)
        self.assertIn("campaignEventHorizonDotCategories", self.dashboard)
        self.assertIn("campaignEventHorizonTypeGroups", self.dashboard)
        self.assertIn("renderOperationsHorizonComposition", self.dashboard)
        self.assertIn("renderOperationsHorizonLegend", self.dashboard)
        self.assertIn("hybrid-events-ops-legend", self.dashboard)
        self.assertIn("hybrid-events-ops-legend-swatch", self.dashboard)
        self.assertIn("campaignEventTypeCode(category.types[0])", self.dashboard)
        self.assertNotIn("hybrid-events-ops-marker-label", self.dashboard)
        self.assertIn("hybrid-events-ops-week-count", self.dashboard)
        self.assertIn("hybrid-events-ops-info", self.dashboard)
        self.assertIn("Event type color legend", self.dashboard)
        self.assertIn("hybrid-events-ops-head-controls", self.dashboard)
        self.assertIn('data-event-type="${escapeAttribute(filter.key)}"', self.dashboard)
        self.assertNotIn("hybrid-events-ops-toolbar", self.dashboard)
        self.assertIn("is-month-start", self.dashboard)
        self.assertIn("Curated high-signal calendar", self.dashboard)
        self.assertIn("Data as of:", self.dashboard)
        self.assertNotIn("hybrid-events-ops-asof", self.dashboard)
        dot_categories_start = self.dashboard.index(
            "const campaignEventHorizonDotCategories"
        )
        dot_categories_end = self.dashboard.index(
            "function campaignEventHorizonTypeGroups(", dot_categories_start
        )
        dot_categories = self.dashboard[
            dot_categories_start:dot_categories_end
        ]
        self.assertEqual(
            re.findall(r'label: "([^"]+)"', dot_categories),
            ["DEBATE", "RALLY / MEETING", "VISIT", "LAUNCH", "OTHER"],
        )
        self.assertIn('horizonKeys: ["media", "other"]', dot_categories)
        composition_start = self.dashboard.index("function renderOperationsHorizonComposition(")
        composition_end = self.dashboard.index(
            "function renderOperationsScheduleRail(", composition_start
        )
        composition = self.dashboard[composition_start:composition_end]
        self.assertNotIn("campaignEventParticipantCount", composition)
        self.assertNotIn("data-hybrid-event-id", composition)
        self.assertIn('aria-hidden="true"', composition)
        self.assertNotIn("×", composition)
        self.assertIn("hybrid-events-watch-material-item", self.dashboard)
        self.assertIn("hybrid-events-watch-addition-group", self.dashboard)
        self.assertIn("hybrid-events-watch-event-node", self.dashboard)
        self.assertIn("MATERIAL CHANGES 0", self.dashboard)
        self.assertNotIn("No material calendar changes", self.dashboard)
        self.assertIn("groupCampaignEventAdditions", self.dashboard)
        self.assertIn("EVENT DETAILS", self.dashboard)
        self.assertIn("PARTICIPANTS", self.dashboard)
        for forbidden in (
            "ELECTION ANCHORS",
            "PARTICIPATION MATRIX",
            "CHANGE FEED",
            "EVENT PULSE",
            "12-WEEK EVENT STRIP",
            "NEXT SIGNALS",
            "EVENT MONITOR",
            "SCHEDULE HORIZON",
            "SELECTED WEEK",
            "CAMPAIGN SCHEDULE",
            "EVENT CALENDAR",
            "EVENT STREAM",
            "12-WEEK HORIZON",
            "NOT INVITED",
            "LIKELY",
            "TENTATIVE",
            "Reliability HIGH",
            "CALENDAR UPDATES",
            "UPDATE TYPES",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.dashboard)


    def test_past_scheduled_events_are_not_silently_completed(self):
        self.assertIn("past_unconfirmed", self.dashboard)
        self.assertIn("PAST · UNCONFIRMED", self.dashboard)
        self.assertIn(
            "Past scheduled events remain scheduled until explicit occurrence evidence confirms they took place.",
            self.dashboard,
        )

    def test_renderer_does_not_surface_opaque_identifiers(self):
        renderer_start = self.dashboard.index(
            "function campaignEventTypeLabel("
        )
        renderer_end = self.dashboard.index(
            "function renderFocusWorkspace(models)",
            renderer_start,
        )
        renderer = self.dashboard[renderer_start:renderer_end]
        for label in ("event_key", "update_key", "source_id"):
            with self.subTest(label=label):
                self.assertNotIn(label, renderer)

    def test_events_css_is_scoped_and_responsive(self):
        self.assertIn(
            "/* CAMPAIGN EVENTS WORKSPACE V1 */",
            self.css,
        )
        self.assertIn(".hybrid-events-workspace", self.css)
        self.assertIn("@media (max-width: 1100px)", self.css)
        self.assertIn("@media (max-width: 760px)", self.css)
        events_marker = self.css.index("/* CAMPAIGN EVENTS WORKSPACE V1 */")
        runoff_marker = self.css.index("/* RUNOFF WORKSPACE REDESIGN V1")
        self.assertLess(events_marker, runoff_marker)
        events_css = self.css[events_marker:runoff_marker]
        for selector in (
            ".hybrid-events-workspace",
            ".hybrid-events-ops-rail",
            ".hybrid-events-upcoming",
            ".hybrid-events-dossier",
            ".hybrid-events-schedule-watch",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, events_css)
        self.assertIn(
            "grid-template-columns: minmax(0, 30fr) minmax(0, 40fr) minmax(0, 30fr)",
            events_css,
        )
        self.assertIn(
            "grid-template-rows: 96px minmax(0, 1fr) 22px",
            events_css,
        )
        self.assertIn("grid-template-rows: 30px minmax(0, 1fr)", events_css)
        self.assertIn("grid-template-rows: 42px minmax(0, 1fr)", events_css)
        self.assertIn("grid-row: 1 / -1", events_css)
        self.assertIn("pointer-events: none", events_css)
        self.assertIn("grid-template-columns: auto minmax(24px, 1fr) auto", events_css)
        self.assertIn(".hybrid-events-ops-week.is-month-start", events_css)
        self.assertIn(".hybrid-events-ops-week-count.is-empty", events_css)
        self.assertIn(".hybrid-events-ops-legend-item", events_css)
        self.assertIn("${renderOperationsHorizonLegend(model)}", self.dashboard)
        self.assertIn("overflow-y: auto", events_css)
        self.assertIn("overflow: hidden", events_css)
        self.assertIn("border-radius: 50%", events_css)
        self.assertIn("-webkit-line-clamp: 2", events_css)

        rail_start = self.dashboard.index("function renderOperationsScheduleRail(")
        rail_end = self.dashboard.index("function renderUpcomingEventRow(", rail_start)
        rail_renderer = self.dashboard[rail_start:rail_end]
        self.assertNotIn("renderOperationsHorizonLegend()", rail_renderer)

        panel_start = self.dashboard.index("function renderEventsPanel(")
        panel_end = self.dashboard.index("function renderFocusWorkspace(models)", panel_start)
        panel_renderer = self.dashboard[panel_start:panel_end]
        self.assertGreater(
            panel_renderer.index("renderOperationsHorizonLegend(model)"),
            panel_renderer.index("hybrid-events-ops-main"),
        )

    def test_events_typography_uses_audited_readability_floor(self):
        events_marker = self.css.index("/* CAMPAIGN EVENTS WORKSPACE V1 */")
        runoff_marker = self.css.index("/* RUNOFF WORKSPACE REDESIGN V1", events_marker)
        events_css = self.css[events_marker:runoff_marker]
        for token in (
            "--hybrid-events-panel-title: 13px",
            "--hybrid-events-primary: 12.5px",
            "--hybrid-events-body: 10.5px",
            "--hybrid-events-meta-size: 9.5px",
            "--hybrid-events-micro: 8.5px",
        ):
            with self.subTest(token=token):
                self.assertIn(token, events_css)
        explicit_sizes = [
            float(value)
            for value in re.findall(r"font-size:\s*([0-9.]+)px", events_css)
        ]
        self.assertTrue(explicit_sizes)
        self.assertGreaterEqual(min(explicit_sizes), 8.5)

    def test_hybrid_javascript_syntax(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for frontend syntax checks")
        subprocess.run(
            [node, "--check", str(DASHBOARD)],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_inline_dashboard_javascript_syntax(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for frontend syntax checks")

        scripts = re.findall(
            r"<script>(.*?)</script>",
            self.index,
            flags=re.DOTALL,
        )
        self.assertTrue(scripts)
        source = max(scripts, key=len)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            encoding="utf-8",
            delete=False,
        ) as handle:
            handle.write(source)
            path = Path(handle.name)

        try:
            subprocess.run(
                [node, "--check", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
