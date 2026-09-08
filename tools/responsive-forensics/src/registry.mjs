export const componentRegistry = Object.freeze({
  masthead: {
    selector: "header.masthead",
    probes: [".brand", ".masthead-tools", "#masthead-countdown"],
    requiredControls: [{ selector: "#masthead-countdown", label: "election countdown" }]
  },
  "what-changed": {
    selector: ".what-changed",
    probes: [".panel-head", ".what-changed-list", ".changes-ledger-scroll"]
  },
  race: {
    selector: ".race-glance",
    probes: [".race-glance-head", ".race-event-controls", "#bars", ".bar-row"],
    state: { tabs: "#race-poll-tabs [role='tab']", selects: ["#hypothesis-select"] }
  },
  status: {
    selector: ".context-strip",
    probes: ["#context-status-cell", ".context-cell"]
  },
  media: {
    selector: ".top-media-pulse",
    probes: [".top-media-tabs", "[data-top-media-panel='overview']", "[data-top-media-panel='coverage']"],
    requiredControls: [
      { selector: "[data-top-media-tab='overview']", label: "Media Pulse Overview tab", maxWidth: 1023 },
      { selector: "[data-top-media-tab='coverage']", label: "Media Pulse Coverage tab", maxWidth: 1023 }
    ],
    state: { tabs: "[data-top-media-tab]" }
  },
  "workspace-controls": {
    selector: ".hybrid-workspace",
    probes: [".hybrid-tabs", "[data-tier2-workspace-control]", "[data-tier3-workspace-control]"],
    requiredControls: [
      { selector: "[data-tier2-workspace-control] select", label: "Tier 2 workspace selector", minWidth: 1024, maxWidth: 1398 },
      { selector: "[data-tier3-workspace-control] select", label: "Tier 3 workspace selector", maxWidth: 1023 }
    ],
    state: { selects: ["[data-tier2-workspace-control] select", "[data-tier3-workspace-control] select"] }
  },
  candidates: {
    selector: "#signal-candidates-panel",
    hash: "#signal-candidates",
    probes: ["#candidate-signals-root", ".candidate-signals-workspace", ".candidate-signals-panel-head"],
    requiredControls: [
      { selector: "[data-tier2-candidate-control] select", label: "Tier 2 candidate selector", minWidth: 1024, maxWidth: 1398 },
      { selector: "[data-tier3-candidate-control] select", label: "Tier 3 candidate selector", maxWidth: 1023 }
    ],
    state: { pressed: ".candidate-signals-candidate-button" }
  },
  agenda: {
    selector: "#signal-agenda-panel",
    hash: "#signal-agenda",
    probes: [".hybrid-agenda-v6-workspace", ".hybrid-agenda-v6-panel-head", ".hybrid-agenda-v6-matrix-wrap"],
    state: { pressed: ".hybrid-agenda-v6-topic-card" }
  },
  issues: {
    selector: "#signal-issues-panel",
    hash: "#signal-issues",
    probes: [".hybrid-agenda-v6-workspace", ".hybrid-agenda-v6-panel-head", ".hybrid-agenda-v6-matrix-wrap"],
    state: { pressed: ".hybrid-agenda-v6-topic-card" }
  },
  events: {
    selector: "#signal-events-panel",
    hash: "#signal-events",
    probes: [
      ".hybrid-events-workspace", ".hybrid-events-ops-rail", ".hybrid-events-ops-filters",
      ".hybrid-events-ops-main", ".hybrid-events-upcoming", ".hybrid-events-dossier",
      ".hybrid-events-dossier-lede", ".hybrid-events-dossier-grid",
      ".hybrid-events-evidence-primary", ".hybrid-events-schedule-watch"
    ],
    state: { pressed: "[data-hybrid-event-id]" }
  },
  runoff: {
    selector: "#signal-runoff-panel",
    hash: "#signal-runoff",
    probes: [".hybrid-runoff-workspace", ".hybrid-runoff-layout", ".hybrid-runoff-history"]
  },
  footer: {
    selector: "#method-disclosure",
    probes: ["#fr27-app-hud-toggle", "#fr27-app-hud-surface"],
    requiredControls: [{ selector: "#fr27-app-hud-toggle", label: "system dock toggle" }]
  }
});

export function selectComponents(raw = "") {
  const names = raw ? raw.split(",").map(value => value.trim()).filter(Boolean) : Object.keys(componentRegistry);
  const unknown = names.filter(name => !componentRegistry[name]);
  if (unknown.length) throw new Error(`Unknown component(s): ${unknown.join(", ")}`);
  return names;
}
