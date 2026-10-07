# FR27 → X publisher

This directory contains the deterministic X publishing system for France 2027 Signal Lab.

Nothing publishes unless the GitHub repository variable `FR27_SOCIAL_ENABLED`
is exactly `true`, or a manual workflow run is explicitly launched with
`publish=true`.

## Publishing model

The production model is text-first.

Daily core queue:

- 08:45 — French campaign-event roundup, when events exist.
- 09:30 Monday — French weekly flagship, resolved at execution.
- 10:15 Tuesday–Sunday — French Issues movers, when qualified and fresh.
- 11:30 — English movers.
- 12:15 Tuesday–Sunday — French Agenda movers, when qualified and fresh.
- 14:30 Tuesday–Sunday — French rotating Issues/Agenda dominance, when eligible.
- 16:45 — French candidate visibility comparison, resolved at execution.
- 18:30 — French conditional Radar Médias, resolved at execution.
- 19:30 — English movers from a distinct family.

Maximum core output:

- French: 6 core posts/day (4 on Monday, including events when present).
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

Issues and Agenda use the latest complete UTC day versus the previous day.
On Monday the French flagship and English movers use the latest complete UTC
Monday–Sunday week versus the preceding complete week. The French flagship
replaces the three specialist slots even if it skips. The incomplete UTC day
is excluded from both families.

The existing 16:45 `candidate_media_pulse_current` product compares canonical
`candidate_visibility_history.json` counts in both `general_visibility` (outside
campaign coverage) and `campaign_attention` (election/campaign coverage). On
Tuesday–Sunday it compares yesterday UTC with the immediately preceding complete
UTC day. Monday replaces that daily comparison with the latest seven complete
UTC days versus the preceding seven. Weekly shares divide summed numerators by
summed denominators; they never average daily percentages.

Eligible candidates still come from the canonical active-monitoring registry:
main/secondary and present upstream. Signals supply current-day reported-evidence
readiness, not metric values. The strongest absolute percentage-point movement
wins, then combined candidate evidence, candidate ID and general-before-campaign
lane order. History must satisfy its existing complete UTC-day contract, end
yesterday UTC and have positive daily denominators for the comparison.

The morning queue still stores only
`candidate_media_pulse_current:slot:{Paris_date}:fr`, with empty text. At execution
it reads fresh history, Signals, registry and routes, checks eligibility,
freshness, identity, the exact canonical French URL and the existing weighted
280-character limit. Unavailable inputs skip without Buffer access or frozen
copy reuse. Successful receipts keep the exact sent text and the existing key
`candidate_media_pulse_current:{candidate_id}:{Paris_date}:fr`.

French Agenda and Issues captions select one observation using the existing
ranking functions. Comparisons retain current/previous evidence and denominators,
percentages and signed changes; dominance describes only the current period.
Public copy uses the existing “jours-sources” vocabulary and natural full labels.
The Issues caveat retains its multilabel meaning. Candidate copy describes
non-exclusive shares of candidate-linked articles, never electoral support.

Issues consume `issue_page_contract.py`: distinct Issue source-days divided by
all accepted relevant-news source-days for the same window. Issues are
multilabel, so their incidences can sum above 100%.

Campaign Agenda consumes `agenda_page_contract.py`: topic source-days divided
by the sum of source-days across all six topics. Polls stay in the denominator;
`polls_race` is excluded only from public ranking. Visible social movement is
current displayed percentage minus previous displayed percentage.

`signal_engine.py` is a legacy article-share/historical-candidate preview tool.
The scheduled V2.1 planner, queue and runner do not import or invoke it. Explicit
legacy helper access lazily imports it for older callers; it is not a fallback
when current authorities fail.

The public wording must describe the actual measurement window.

## Internal links

Every quantitative core post links to the corresponding canonical FR27 page.

Canonical URLs are resolved from `route_registry.json` rather than from a
separate social-media route map.

Examples:

- candidate signal → candidate dossier;
- issue signal → issue dossier;
- Agenda signal → Agenda dossier.

The daily event roundup links to `https://france2027.app/#signal-events`: the
registered French dashboard and its existing Campaign Events view. Its full URL
is always retained; long roundups deterministically list fewer events.

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

Every included line retains its complete display title. The builder keeps the
header and canonical link, and omits whole excess event lines to respect the
weighted X limit of 280. If no complete line fits, it skips the roundup.

## Daily queue

Exact slots and the scheduler heartbeat share `core_slot_timeliness` with
`MAX_CORE_LATENESS_MINUTES = 60`: live execution is eligible only from the
Europe/Paris target time through exactly 60 minutes afterward, inclusive.
Expired invocations succeed as intentional NOOPs without Buffer access or
state writes; their items remain pending. Manual `publish=false` maps to
`--dry-run` and permits stale previews with `STALE / WOULD_NOT_PUBLISH_LIVE`
and lateness printed. Manual live execution has the same time gate.

The heartbeat remains `2,17,32,47 8-20 * * *` in Europe/Paris, selecting the
oldest eligible pending core item and publishing at most one per invocation.

`social/daily_queue.py` builds the morning queue for the current Paris date.
Events, Issues, Agenda, dominance and English text remain immutable. The 16:45
candidate, 18:30 Radar and Monday 09:30 flagship entries are empty instructions
resolved only when their slots execute. The flagship verifies one Git revision,
matching producer timestamps, exact weeks and published-page parity.

A same-day rebuild returns the already persisted queue rather than selecting
new core posts.

### Event-driven morning planning

`Publish FR27 to X` follows successful main-branch completions of the News Wire,
polls, candidate-universe, issue, agenda and candidate-family workflows, plus
Campaign Events validation. These completions are retry opportunities. None is
assumed to be the last producer. The existing **08:25 Europe/Paris** build
schedule remains a fallback. Failed/cancelled upstreams, pull-request runs,
forks and other branches are inert. Every automatic run still requires
`FR27_SOCIAL_ENABLED == 'true'`.

The frozen-input graph is:

| Queue input | Author / dependency | Role |
| --- | --- | --- |
| `issue_coverage_history.json` | Publish issue family, reconstructed from retained/current News Wire | Frozen Issues and English products |
| `agenda_coverage_history.json` | Publish agenda family, reconstructed from retained/current News Wire | Frozen Agenda and English products |
| `campaign_events.json` | Reviewed manual events/updates, institutional seeds and sources; candidate-universe rebuilds on registry changes; Validate campaign events checks synchronization | Frozen event roundup |
| `route_registry.json` | Poll, issue, agenda and candidate publication writers | Canonical frozen destinations |
| `recent_changes.json` | News Wire and polls writers | Read for diagnostics; `max_updates=0` supplies no frozen content |
| `candidate_visibility_history.json`, `candidate_signals.json`, candidate registry | News/polls/universe and candidate-family writers | Optional morning preview; Candidate content remains late-bound |

Live event, fallback and manual `build-queue` runs acquire the existing
`production-data-update` lock **before checkout**, retaining it through input
verification, queue construction, optional Buffer handoff and state persistence.
The separate outer `fr27-social-publish` lock still serializes all social state
writers. Both use `cancel-in-progress: false` and `queue: max`; readiness never
depends on queue ordering or on GITHUB_TOKEN pushes triggering a push workflow.

`planner_readiness.py` starts daily planning at 06:00 Paris, requires today's
news snapshot to be no more than six hours old (and never future-dated), requires
both histories to match its exact timestamp, then runs each history/page
builder's read-only `--check` and the route-registry check. Campaign Events are
reproduced locally into a temporary file from their authoritative inputs and
compared with the tracked artifact. No remote source or Buffer is fetched.
Long-lived event timestamps are allowed when content remains synchronized.

A failed barrier resolves to `planner-deferred`: no persistent social state is
accessed and no Buffer configuration, reconciliation or scheduling step runs.
A successful barrier writes a temporary snapshot digest receipt. The live build
rechecks those digests and records the receipt in the frozen queue. Repeated
builds preserve both frozen text and the original receipt. An existing same-day
queue without a readiness receipt is refused, rather than being relabeled after
its inputs change; it can safely roll over on a later day subject to the existing
unresolved-delivery guard. Dry-run builds retain their existing preview behavior.

Missing/false `FR27_BUFFER_SCHEDULING_ENABLED` permits queue construction and
persistence without Buffer credentials or API calls. Explicit true permits the
existing scheduled-delivery path after readiness and receipt validation. Existing
receipt recovery, late-bound products, shareNow recovery and both 60-minute
lateness guards remain unchanged. This implementation does not activate either
production flag.

### Manual weekly catch-up

The regular French flagship remains Monday at **09:30 Europe/Paris**. A missed
Monday may be recovered only on the immediately following Tuesday or Wednesday
using `workflow_dispatch`, mode `weekly-flagship-catchup`. There is no scheduled
catch-up trigger. `publish=false` previews the exact validated text, target
Monday, completed Monday–Sunday week, product ID and weighted length;
`publish=true` permits Buffer publication and receipt persistence. No arbitrary
historical replay or clock override is supported.

For Tuesday 2026-10-06 (also Wednesday 2026-10-07), the target Monday is
2026-10-05 and the completed week is 2026-09-28 through 2026-10-04, compared
with 2026-09-21 through 2026-09-27. This is an out-of-band recovery; it never
builds or rewrites today's immutable queue or restores Monday specialists.

Catch-up requires one clean Git revision, matching news/Issue/Agenda refresh
timestamps from the current UTC day, complete histories through yesterday UTC,
and candidate history and Issue manifest dates from that same refresh day.
Both page-source families must share an analytical cutoff within the Monday
through execution-day recovery interval.
The normal authority, evidence, source-family and compact 280-character checks
still apply. The target history snapshots are bound to the derived Monday and
reconciled against `build_issue_period_metric` and `build_agenda_period_metric`
over both exact calendar weeks, checking identities, source-days, denominators,
raw shares and shared displayed rounding. Live destination cards reconcile
separately to their current generated comparison window, which may have advanced
since Monday. Selected pages retain canonical-route, refresh-date and semantic
content-hash verification using the route registry's own HTML normalization.
Any exposed target dates in historical HTML ledgers must also match the canonical
histories. Missing old-period HTML is permitted when the authority proof passes.
Normal Monday page validation still requires its exact completed-week cards.
Artifacts are never regenerated by catch-up.

An uncommitted development checkout still fails the publication guard. If all
canonical authority and page checks pass first, dry-run prints the verified
candidate copy with `publishable=false` and returns failure; it never calls
Buffer or writes state. A successful preview requires a clean, stable checkout.

The shared `planner.weekly_flagship_published_weeks` ledger skips an existing
successful product receipt. Exact recent Buffer text duplicates resolve using
the regular `buffer-existing` receipt convention. A successful send or exact
duplicate resolution stores `product_id`, `revision`, `published_at` and
`buffer_post_id`; failed publication and preview write no state. Live workflow
execution requires existing `social-assets` state and uses the same serialized
publisher concurrency group.

Direct preview with a loaded persistent state file:

```sh
python -B social/weekly_flagship_catchup.py --state /tmp/fr27-social/input-state.json --state-output /tmp/fr27-social/output-state.json --dry-run
```

For live execution omit `--dry-run` and provide Buffer configuration. The CLI
uses the actual execution clock; it exposes no date or historical-week input.

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

New queue items also expose the additive identity fields from
`queue_metadata.py`: `post_type`, `family`, `metric_id`, `aggregation_unit`,
`denominator_id`, `window_mode`, `window_start`, `window_end`,
`comparison_start`, `comparison_end`, `rank_kind`, `canonical_url`, `late_bound`.
Newsroom values are copied from canonical product objects without new metric
arithmetic. `rank_kind` retains the existing `movers`/`dominance` vocabulary.
Candidate and Radar boundaries are unresolved/null until successful execution;
Candidate's URL is also unresolved until fresh selection. The composite flagship
has no single metric, aggregation unit or denominator. Resolved Candidate metadata
records the selected lane, horizon and comparison dates. Dominance and Radar have
no dated comparison pair; events have no analytical metric/window.

Queue, planner and social state stay at schema version 1. Existing readers
already accept extra fields. Missing metadata is valid for old items; loading
does not enrich or rewrite historical queues or receipts. Published status,
Buffer IDs, seen registries, Radar fingerprints and flagship week receipts stay
intact. Rebuilding today's queue returns the same object, including old items.

Issues and Agenda newsroom products may exceed 280 weighted X characters
because the connected X account has Premium long-post capability.
`newsroom_products.py` applies a conservative 1000 weighted-character FR27
editorial safety ceiling for these products; this is an internal editorial
rule, not the platform maximum.

Compact products retain their existing 280-character contracts unless
explicitly migrated: Candidate Media Pulse, Radar Médias, weekly flagship,
dynamic developments, campaign-event copy, legacy/visual captions and generic
short-form social helpers. `social_publish.py` therefore keeps its generic
`MAX_X_WEIGHTED_LENGTH = 280` contract.

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
