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

3. Two events are comparable only if their `scenario_key` matches (same round, same
   candidate configuration, same hypothesis). When uncertain, treat them as incompatible.
   **Under-inclusion is safer than a misleading trendline.**

4. No missing value is ever invented. Footnote/citation markers are stripped before
   parsing numbers (`"34[a]"` → `34`, `"12,5 %"` → `12.5`, `"–"` → missing). If a cell
   can't be parsed cleanly and unambiguously, the field is omitted rather than guessed.

## Build rules (non-negotiable)

5. One vertical slice at a time: one widget or capability per increment, smallest
   possible implementation, run it, inspect real output, then stop and review before
   continuing.

6. No file is created unless it was named up front for that increment. If a new file
   seems necessary, that's a stopping point requiring explicit review — not something
   done silently.

7. No README, test suite, config system, validator framework, or folder structure until
   there are at least 3 working widgets, and it's been deliberately decided to add one.

## Non-goals (always true)

8. No polling averages. No forecasts. No voting advice. No sentiment/ideological
   scoring. Descriptive only — the dashboard reports what was published, nothing more.

## Recent Changes Ledger (`recent_changes.json`)

The Phase 1 ledger is a generated view over the existing public datasets. It does not
expand the five-feed election-news source universe. `items` contains at most 12 unique
changes from a 14-day inclusive Paris-date window, newest first.

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

---

## Build stages

Each stage must be visibly working — real data rendered in the browser — before the
next one begins.

- **Stage 1:** Poll ingestion + normalization into complete poll events. Latest poll
  event rendered as candidate bars. Basic trendline for comparable events.
- **Stage 2:** Freshness Watch + Poll Institute Roster, derived from the same dataset,
  no new source required.
- **Stage 3:** Full dashboard shell/layout wrapped around the working widgets.
- **Stage 4:** Election Clock (static key dates) + Ballot Access Watch (hand-maintained
  status).
- **Stage 5:** Latest Signals / Data Dock — a log of the pipeline's own update runs.
- **Stage 6 (optional):** Search Attention (search interest data), Market Signal
  (prediction market data), each evaluated on its own merit before adding.

A stage does not expand until the previous one has real data, visible output, no
invented values, working source links, and is genuinely ready to build on.
