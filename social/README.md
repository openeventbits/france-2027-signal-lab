# FR27 → X publisher

This directory contains the deterministic X publishing system for France 2027 Signal Lab.

Nothing publishes unless the GitHub repository variable `FR27_SOCIAL_ENABLED`
is exactly `true`, or a manual workflow run is explicitly launched with
`publish=true`.

## Publishing model

The production model is text-first.

Daily core queue:

- 08:45 — French campaign-event roundup, when events exist.
- 10:15 — French quantitative signal.
- 11:30 — English quantitative signal.
- 12:15 — French quantitative signal.
- 14:30 — French quantitative signal.
- 16:45 — French quantitative signal.
- 19:30 — English quantitative signal.

Maximum core output:

- French: 5 posts/day.
- English: 2 posts/day.

Dynamic French developments are checked separately at approximately:

- 09:05
- 13:05
- 17:05
- 20:05

Each dynamic check can publish at most one item and the persistent daily
quota is three dynamic posts per Europe/Paris calendar day.

Weak, stale or cooldown-blocked quantitative signals are suppressed rather
than replaced with filler.

## Quantitative lanes

The immutable daily queue can select from three quantitative families:

1. Candidate visibility
2. Issues / Enjeux
3. Campaign Agenda

The signal engine uses complete UTC history through the previous UTC day.
The current incomplete UTC day is excluded.

Candidate visibility is a share of candidate-linked campaign coverage.
It is not polling, support, sentiment or a forecast.

Issues use the accepted relevant-news corpus as denominator and are
multilabel, so issue shares can sum above 100%.

Campaign Agenda uses classified Agenda items and a single-label denominator.
`polls_race` is excluded from social quantitative selection.

Supported comparison horizons include:

- daily: latest complete day vs previous complete day;
- weekly: latest 7 complete days vs previous 7 complete days;
- internal `four_week`: 14 complete days vs previous 14 complete days.

The public wording must describe the actual measurement window.

## Internal links

Every quantitative core post links to the corresponding canonical FR27 page.

Canonical URLs are resolved from `route_registry.json` rather than from a
separate social-media route map.

Examples:

- candidate signal → candidate dossier;
- issue signal → issue dossier;
- Agenda signal → Agenda dossier.

The daily event roundup is intentionally linkless.

Dynamic developments use the original publisher/source URL.

## Event roundup rule

Scheduled or confirmed events occurring today in Europe/Paris are eligible
for the morning roundup.

If the event has a known clock time:

`19h00 · Rencontre avec Raphaël Glucksmann à Marseille`

If the event time is unknown, the event remains in the roundup but no time
placeholder is printed:

`Gabriel Attal dans « La parole est à vous » sur France 3`

Never print `Heure non précisée` or an equivalent placeholder.

Timed events sort before untimed events.

## Daily queue

`social/daily_queue.py` builds an immutable queue for the current Paris date.

A same-day rebuild returns the already persisted queue rather than selecting
new core posts.

Each queue item records:

- locale;
- slot;
- lane;
- deterministic key;
- exact text;
- score when applicable;
- pending/published state;
- publication timestamp;
- Buffer post ID.

A successful or duplicate-resolved publication updates the queue item only
after Buffer resolution.

## Planner state and cooldowns

The unified social state contains a nested `planner` object.

It records:

- published quantitative signals;
- dates on which the roundup was published;
- dynamic developments;
- the immutable daily queue.

Current cooldown policy:

- daily horizon: 1 day;
- weekly horizon: 7 days;
- 14-vs-14 horizon: 14 days;
- same entity across horizons: 2 days.

The roundup is limited to once per Europe/Paris date.

## Dynamic developments

`updates` publishes source-linked campaign developments and campaign events.

Polling and runoff changes are excluded.

Google News RSS wrapper URLs are resolved to publisher URLs before
publication. An unresolved wrapper fails closed for that item.

Near-duplicate developments are clustered conservatively.

Fresh-update diversification limits same-candidate repetition.

The persistent dynamic quota is three posts/day.

## Buffer and duplicate recovery

Before publishing, the system checks recent Buffer content for exact text
duplicates.

If Buffer already contains the exact post text, the post is treated as
resolved instead of being created again. This protects against the case where
Buffer accepted a post but the subsequent state commit failed.

Required configuration:

GitHub secret:

- `BUFFER_API_KEY`

GitHub repository variables:

- `BUFFER_ORGANIZATION_ID`
- `BUFFER_X_CHANNEL_ID`
- `FR27_SOCIAL_ENABLED`

Keep `FR27_SOCIAL_ENABLED` unset or false until activation is explicitly
approved.

## Persistent state

Publishing state is stored at:

`social/x/state.json`

on the `social-assets` branch.

On the first activation, the manual `bootstrap` mode snapshots existing
recent changes and campaign-event IDs so historical material is not dumped
onto X.

The workflow can create `social-assets` from zero during the approved live
bootstrap step.

Live bootstrap is create-once. If persistent `social-assets` state already
exists, a live bootstrap fails closed rather than replacing planner history,
cooldowns, queue state, or publication ledgers.

Dry runs do not persist state.

## Workflow safety

`.github/workflows/publish-x-fr.yml` uses one serialized concurrency group:

`fr27-social-publish`

Scheduled runs are inert unless `FR27_SOCIAL_ENABLED=true`.

Manual workflow dispatch defaults to:

- `mode=full-dry-run`
- `publish=false`

The full dry run:

- bootstraps temporary state;
- builds the queue;
- previews every generated core slot;
- previews dynamic updates;
- does not call Buffer;
- does not modify persistent state.

## Screenshots

Custom social-card renderers are not part of the v2 production workflow.

`capture_social_panel.py` is retained only as a dormant direct-panel capture
helper. No screenshot lane is currently scheduled.

If screenshots are added later, they should use actual FR27 interface panels
and must be validated against the exact measurement window of the associated
post before activation.

## Activation sequence

Do not activate directly from a development worktree.

Required sequence:

1. Review the complete v2 diff.
2. Commit and push the feature branch only after explicit approval.
3. Merge while `FR27_SOCIAL_ENABLED` remains unset/false.
4. Run the GitHub `full-dry-run`.
5. Review the generated queue/artifact.
6. Configure and verify Buffer IDs if needed.
7. Run the approved live `bootstrap` to initialize `social-assets`.
8. Keep publishing disabled until the final explicit activation decision.
9. Only then set `FR27_SOCIAL_ENABLED=true`.

## Dependencies

The social text publisher pins:

- `googlenewsdecoder==0.2.1`
- `selectolax==0.4.13`

Playwright is an optional dependency for the dormant panel-capture helper and
is not installed or invoked by the current production X workflow.
