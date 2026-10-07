# Agenda and Issues live data, Phase 1

## Inspection and authority

The isolated branch started from origin/main `0c7880154977bf605554d6e1f110ad340f275adc`.
News Wire runs hourly at minute 23 and on manual dispatch. Its completed runs
previously triggered Agenda, Issues, Candidates, and X. Agenda and Issues also
follow polls and candidate-universe updates. X treats upstream completion as a
retry opportunity, rather than a readiness barrier. All production writers
retain `production-data-update`, `cancel-in-progress: false`, and `queue: max`.

Agenda's static builder reads News Wire, Agenda coverage history, candidate
agenda history, candidacy/route data, its previous manifest, and the site shell.
Issues reads the equivalent Policy Agenda/Issues history inputs and candidate
routes. Both retain current, historical, bilingual, canonical and sitemap routes.
The existing browser scripts sort/filter static cards and switch history modes.

`campaign_agenda` is single-label campaign-theme classification. `policy_agenda`
is multilabel issue classification. Both contain base counts, publisher names,
bounded supporting articles, and complete 30-calendar-day evolution series with
a partial final UTC day and two preceding complete 7-day windows. Base rolling
inventory counts may include the oldest partial UTC day before the evolution
calendar starts. These are separate contracts, not interchangeable totals.

Agenda hub shares divide topic source-days by all six canonical topics'
source-days. Issues hub incidence divides issue publisher-days by accepted
relevant-news publisher-days; percentages overlap. The Issues companion panel
uses single-label Campaign Agenda **article** composition. Shared page metric
functions remain the calculation authority; no classifier is rerun.

Agenda history schema 1.0 stores complete UTC days, all six canonical topics,
classified-item and topic-source-day daily denominators, retained source snapshot
identities and bounded historical evidence. Issues history schema 1.0 stores
the accepted article corpus, multilabel issue daily article/publisher counts,
article shares and retained snapshot identities. Its article shares do not
replace the hub's source-day incidence denominator. Both histories still use
retained Git snapshots and exclude the current partial UTC day.

`CLOUDFLARE_IN_REPO=false`: repository-wide searches found no Cloudflare Worker,
Wrangler, dispatch integration, KV, R2 or D1 implementation. External dispatches
to the existing News Wire workflow will get projections automatically. No
infrastructure or secrets are added.

## New publication contract

`build_agenda_live_projection.py` and `build_issue_live_projection.py` accept
`--news`, `--output`, and `--check`. They validate published source contracts,
project canonical IDs without reclassification, use source `generated_at`, and
write compact, sorted-key JSON by atomic replacement. Identical bytes are not
rewritten. There is no network, current-clock, browser, or Git-history input.

`agenda/live.json` and `enjeux/live.json` have schema version 1.0, family/source,
`generated_at == source_snapshot`, period/window/partial-day metadata, base and
calendar-rolling counts, denominator identities, canonical topic daily data,
shares/movement, and at most six supporting evidence records. Both languages
use the same artifact. `counts.rolling_assignment_count` sums evolution topic
items; base `classified_item_count` and Issues `label_assignment_count` retain
their News Wire meanings. Agenda publisher counts retain the page's base
publisher meaning; Issues cards retain evolution publisher counts.

News Wire builds and checks both temporary projections from `/tmp/news_wire.json`
before promotion. Promotion validates the entire set before atomic file
replacement. The existing single data commit stages both artifacts, regenerates
them after rebase, reconciles them in amend scope, and performs final checks.
Source/projection publication is atomic at the Git commit boundary. A purely
volatile fetch leaves the committed source and projection bytes unchanged;
missing/stale projections are repaired from the committed source. Policy Agenda
also participates in News Wire semantic change detection.

The current hub markup carries explicit canonical-ID and live-field hooks.
Frontend fetch uses `cache: "no-store"` and `credentials: "same-origin"` once on
load. Complete schema/source/day/count/denominator/DOM-map validation happens
before any update. Older-than-static payloads are rejected. Successful fetches
update metrics, cards, signals, state, 30-day bars, movement/composition numbers
and periods, then reapply the selected sort and filter. Existing nodes, links,
labels, structured SEO, method notes and history content remain in HTML.
Fetch/HTTP/JSON/schema/identity failures silently retain the entire static DOM.

Only News Wire is removed from the two family upstream lists. Daily static
refresh stays at Issues 11:17 UTC and Agenda 11:53 UTC; other upstreams stay.
No workflow is added, and the candidate family, polling semantics, X cadence,
global queue, detail pages and historical storage remain unchanged. Removing
two direct fan-outs saves up to 48 full family runs per day at the hourly News
Wire cadence, plus two per successful external/manual refresh. Other triggers
and periodic static refreshes still run.

## Validation and limits

`test_live_projections` tests deterministic contracts, canonical IDs, source
identity, rejected malformed inputs, atomic failure, explicit CLI checks, no
reclassification, and executes the real workflow promotion code for publication,
timestamp-only no-op, stale repair, and rejection before source promotion.
Existing workflow/queue/metric/route/publication/search/frontend/X suites are
also required. The News Wire workflow runs the pure projection suite.

`test_live_projection_frontend` is an optional test-only Playwright Chromium
suite for both actual FR/EN hub DOMs, all four sorting modes, fetch/HTTP/JSON/
schema/source/date/count/mapping failures, preserved routes, filtering, microbars,
and history fetch isolation. It requires an installed test browser; this adds
no production dependency or additional scheduled Actions job.

Detail pages, source-linked observation lists and candidate associations remain
static snapshots, refreshed by the family workflows. Newly qualifying URLs
still require static family publication. History storage is deliberately unchanged.
The compact evidence records are available for a later isolated evidence-list
enhancement. Route hashes/sitemaps are refreshed once for changed static hubs,
not on every News Wire run.

## Subsequent phases

Phase 2: define candidate projections against an explicit dependency identity
covering polls, candidacy, claims, attention, campaign events, visibility/agenda
history and publication manifest. Only remove candidate fan-out once every
producer can regenerate a source-consistent projection with existing JSON-fetch
fallback and equivalent contract tests.

Phase 3: finalize canonical observations after each complete UTC day closes.
Store immutable daily artifacts with schema/taxonomy version, UTC date,
source snapshot identity, complete/missing status, canonical per-topic item and
publisher-day counts, accepted-corpus denominators, and bounded evidence IDs.
Preserve single-label Agenda and multilabel Issues semantics. Define late-arrival
corrections, idempotent finalization, atomic publication and completeness checks.
Backfill from retained snapshots and verify parity before switching historical
builders to the daily artifacts; only then remove Git-history reconstruction.

Inventory last-seen/generated timestamps and other bookkeeping changes retain
the committed public News Wire snapshot unless its semantic projection changes.
Live artifacts are chosen against that public-source decision, rather than the
broader inventory/health/history commit decision. Executed promotion tests cover
both bookkeeping-only updates and stale projection repair in such an update.
