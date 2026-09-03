# France 2027 Signal Lab — Contract

---

## Data rules (non-negotiable)

1. A poll event is atomic: pollster + fieldwork dates + round + hypothesis + ALL candidates
   in that poll, nested together. A candidate score must never be stored as an independent
   row separate from its poll event.

2. `event_id` is deterministic:
   `SHA256(normalized_pollster + fieldwork_start + fieldwork_end + round + normalized_hypothesis + source_url)`
   Rerunning ingestion against unchanged source data must produce the same IDs — no duplicates, ever.
   The ID must never depend on row number, array position, or ingestion time.

3. Two events are comparable only if their `scenario_key` matches. The current
   `scenario_key` is deterministic from the round and the sorted normalized candidate
   configuration. It does not depend on the hypothesis label, pollster, fieldwork dates,
   source URL, array position, or ingestion time. When uncertain, treat events as
   incompatible. **Under-inclusion is safer than a misleading trendline.**
4. No missing value is ever invented. Footnote/citation markers are stripped before
   parsing numbers (`"34[a]"` → `34`, `"12,5 %"` → `12.5`, `"–"` → missing). If a cell
   can't be parsed cleanly and unambiguously, the field is omitted rather than guessed.

### Commission notice coverage

Every Commission des sondages notice already classified as relevant presidential
voting-intention evidence has exactly one corpus-coverage state:

- `parsed`: a published event carries the notice's direct `official_notice_id` provenance;
- `reconciled`: an otherwise unparsed notice has one deterministic published-wave match;
- `unresolved`: neither condition is satisfied, including ambiguous matches.

Only `unresolved` relevant notices produce poll-coverage warnings. Parser or document
support remains a separate engineering condition. Reconciliation requires exact normalized
pollster identity, exact fieldwork start and end dates, and round compatibility; optional
sample, commissioner, and publication metadata may only disambiguate multiple exact-window
waves. Irrelevant notices never receive a coverage state.

## Change and publication discipline

Current change, validation, writer, and publication procedures are documented in
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).

Those procedures include bounded change scope, explicit expected-file scope, assertion
classification, validation before promotion, exact writer and staged scope, safe
reconciliation with a moving `main`, and scheduled production proof where required.

Early build-stage sequencing is historical project-development material, not a current
product invariant. Repository history preserves that development history.

## Non-goals (always true)

5. No polling averages. No forecasts. No voting advice. No sentiment or ideological
   scoring. FR27 is descriptive: it publishes source-linked evidence and deterministic
   derived signals, but does not convert them into electoral probabilities,
   recommendations, or predictions.

## Candidate universe authority

`candidate_candidacy_status.json` is the sole authority for canonical candidate identity
and candidacy status. Its complete universe retains stored `main`, `secondary`, and
`hidden` identities. Current active monitoring is the shared registry projection of
`present` candidates whose stored display tier is `main` or `secondary`; consumers must
use `active_candidate_records()`, `active_candidate_ids()`, or
`active_candidate_names()` rather than reproducing that rule.

Evidence remains source-derived. Poll ingestion preserves every clean candidate reported
by a poll source, regardless of Registry membership. Candidate Attention covers the
current active field and distinguishes observed Pageviews from
`unavailable_no_personal_article` without inventing zero views. Claims queries the
current active field, while accepted reviews and frontend filters remain evidence-oriented
and may retain historical canonical candidate associations. Candidate Signals preserves
the complete canonical identity universe separately from its effective active-monitoring
projection.

### Candidate discovery

Candidate-universe discovery may use multiple verified source classes, with attributable
first-party evidence preferred where available. Discovery does not override registry
authority: stable identity, conservative status transitions, retained last-good records,
fail-closed ambiguity, and source-linked provenance remain mandatory. Wikipedia may serve
as fallback or corroborating evidence. Discovery changes must not alter downstream
active-monitoring semantics.
## Recent Changes Ledger (`recent_changes.json`)

The ledger is a generated view over the existing public datasets and the configured
election-news source universe. `items` contains every qualifying unique
change from a 14-day inclusive Paris-date window, newest first.

Each item has a stable `id`, one of `campaign`, `polling`, `runoff`, `fact_check`, or
`legal`, a source-linked headline and summary, explicit `published_at`, `event_date`,
`detected_at`, and `generated_at` provenance, plus `trusted_change_at` and
`trusted_change_date_kind`. Only `trusted_change_at` controls public ordering and date
groups. Allowed trusted kinds are source publication, official event, first seen,
fieldwork ended, review publication, and ruling/decision. Detection and generation time
never become a political-change date. Primary and supporting sources, icon key,
candidate identifiers, and an existing dashboard destination are retained where
available.

`last_successful_check_at` is the check that produced the published ledger artifact.
No-change workflow runs do not alter it because GitHub Pages has no independent channel
for publishing a check timestamp without changing repository content.

## Related documentation

- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — measurement semantics and evidence boundaries.
- [`docs/DATA_AND_PROVENANCE.md`](docs/DATA_AND_PROVENANCE.md) — data lanes, provenance, and freshness.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — executable contracts and publication architecture.
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — change classification, production safety, validation, and incident response.
