# Task 05 — Candidate Trace / Signal Braid v1

Task 05 is the first multi-lane TRACE composition inside the existing public
Candidate family:

```text
validated fixed production artifacts (read only)
-> explicit canonical candidate ID
-> exact 28-complete-UTC-day evidence slice
-> established qualifying component or poll-package event
-> Task 01 Candidate TRACE
-> Task 02 presentation model and frozen shell
-> Signal Braid TRACE FIELD
-> local 1280 x 720 PNG
```

The detector is `signal_braid.v1`; `signal_braid` is only the internal field
renderer discriminator. It is not a public family, score, forecast, ranking,
popularity measure, viability measure, momentum measure, synthetic index, or
dashboard summary.

## Authoritative sources and lane semantics

The live adapter accepts only an explicit canonical ID from validated
repository-root `candidate_candidacy_status.json` and reads fixed paths. It has
no arbitrary-source-path option, fuzzy lookup, fallback candidate, writer,
network request, rebuild, or import-time content read.

Exactly four lanes are structurally present:

- **Media** — `candidate_visibility_history.json`, validated by
  `candidate_visibility_history_contract.validate_candidate_visibility_history`.
  The selected quantity is only
  `campaign_attention.daily_series[].record_count`: daily retained
  candidate-linked records in the established election/campaign scope.
- **Wikipedia** — `candidate_attention.json`, validated by
  `candidate_attention_contract.validate_candidate_attention`. The lane uses
  the exact raw daily `views` observations for `fr.wikipedia.org`, pageviews,
  all-access, user, daily. Pageviews are not unique people, popularity,
  sentiment, approval, support, or voting intention.
- **Agenda / Issues** — `candidate_agenda_history.json`, validated by
  `candidate_agenda_history_contract.validate_candidate_agenda_history`. The
  selected evidence keeps the existing policy and campaign taxonomy IDs and
  all exact counts, including zeros. The field displays only categorical topic
  incidence in separate POLICY and CAMPAIGN matrix sections. Each canonical
  topic has one fixed labeled sub-row, and a same-size mark records incidence
  on each date; count never controls height, opacity, area, rank, or intensity.
  Dates before a candidate's `tracking_start` are
  `not_observed`, never manufactured zeros.
- **Poll Tests** — the established package-level `poll_history` in
  `candidate_signals.json`. Task 05 validates a narrow schema-1.5 read adapter
  and package-key reconciliation without importing
  `build_candidate_signals.py`. One package key is the JSON tuple of pollster,
  fieldwork start, fieldwork end, and sample size. Multiple accepted
  first-round hypotheses remain one package with `hypothesis_count`; candidate
  scores, ranges, ranks, averages, trends, and unrelated hypotheses are not
  selected. Package keys are decoded and reserialized canonically; equivalent
  JSON spellings collapse to the same semantic package tuple, while conflicting
  duplicate facts fail closed. The candidate-specific history period must match
  its complete observation bounds before the parent-window slice is selected.

Media and Agenda both derive from candidate-linked news evidence. They remain
separate because Media is daily retained record count while Agenda is
categorical topic association. They are not statistically or source
independent, and simultaneous movement is not corroboration.

## Common calendar, availability, and failure behavior

The common end is the earlier validated complete-day `data_as_of` from Media
and Candidate Attention, provided Agenda History covers that date. The current
UTC day is excluded by the authoritative complete-day source and an independent
UTC validation guard requires the common end to precede today's UTC date. The closed
window starts 27 days before that end, contains exactly 28 UTC calendar dates,
and is never interpolated. Agenda may cover a later incomplete current date;
that date cannot enter the braid.

If the exact window cannot be established, selection is validly suppressed as
`no_common_28_day_window`. Each of the four lane rows remains structurally
present. `observed` includes numeric zero; `not_observed` means no accepted
discrete record or a pre-tracking date; `unavailable` means the source cannot
provide an observation; `not_applicable` is reserved for explicit upstream
N/A. Broken continuity, malformed values, arithmetic inconsistency, unknown
candidate identity, and invalid child relationships are errors, not
suppressions.

## Eligibility and deterministic findings

Signal Braid is a composition of established evidence, not a new significance
detector. A candidate requires:

1. one exact canonical controlled ID;
2. at least two fully observed 28-day longitudinal lanes among Media,
   Wikipedia, and Agenda (observed zero counts); and
3. either a valid eligible Flash/Shift whose complete 14-day window is
   contained unchanged in the parent, or at least one accepted first-round
   poll package whose `fieldwork_end` lies in the parent window.

The remaining valid suppressions are `insufficient_longitudinal_coverage` and
`no_qualifying_signal`. Agenda incidence and Coverage Anatomy never qualify the
parent on their own, and no new threshold exists.

When Flash/Shift qualifies it supplies one fixed public-facing finding:

- `event_amplified` -> `WIKIPEDIA ATTENTION SHOWED A FLASH PATTERN.`
- `sustained_rise` -> `WIKIPEDIA ATTENTION SHOWED A SHIFT · RISE PATTERN.`
- `sustained_decline` -> `WIKIPEDIA ATTENTION SHOWED A SHIFT · DECLINE PATTERN.`

If poll packages alone qualify, the finding is `TESTED IN N FIRST-ROUND POLL
PACKAGE(S) THIS WINDOW.` If both qualify, Flash/Shift supplies the finding and
poll-package count may appear as factual qualifier copy. No cross-lane or
causal finding is generated.

For `signal_braid.v1`, the renderer also validates the finding, optional
qualifier, and visible date label against these deterministic mappings and the
canonical TRACE window. These strings remain outside identity, but arbitrary
replacement prose or a contradictory displayed interval cannot render.

## Child integration and identity

Task 04 selection and validation are called directly; its constants and
classifier are not duplicated. An eligible, contained child contributes only
detector ID, child TRACE key, exact child observation window, and classification
code. A suppressed Task 04 result adds no annotation and does not remove raw
Wikipedia observations.

A Task 03 child must be a valid `coverage_anatomy.v1` Candidate TRACE for the
same candidate. Its complete evidence window must equal its TRACE window and
fit wholly inside the parent unchanged. A compatible child renders only a
restrained media-lane bracket. Its full card, prose, and metrics are never
copied or recomputed. Incompatible live evidence is reported but unselected.

The Task 01 identity slice contains only schema/family/detector, canonical ID,
exact parent window, the locked calendar and lane semantics, selected 28-day
observations, selected poll-package facts, and actually rendered narrow child
references. A rendered child TRACE key is identity material. Display name,
generated timestamps, language, findings, qualifiers, renderer version,
taxonomy labels, source URLs, other candidates, full source payloads, unused
history, poll scores, headlines, publishers, incompatible/suppressed children,
and geometry are excluded.

## Visual semantics

Only the TRACE FIELD inside the frozen Task 02 shell changes. A shared
28-column grid makes the same horizontal position mean the same UTC date.
Media and Wikipedia each display their own named unit and local scale. Agenda
uses a collision-safe categorical incidence matrix with fixed topic sub-rows
and one presentation-only label per topic. Poll packages use equal-weight neutral
fieldwork intervals plus a small endpoint at `fieldwork_end`; an interval that
starts before the parent window is clipped with a continuation cue while its
evidence dates remain intact.

There is no common numeric y scale, vertical causal connector, radar, gauge,
combined score, ranking, comparable heatmap, portrait, event red, or
candidate/party color. Motion is unnecessary because all selected time is
visible at once.

## Frozen fixture and commands

The fixture candidate is `synthetic-candidate-alpha`, 2026-08-04 through
2026-08-31. Its Media total is 211 records and Wikipedia total is 26,800 raw
pageviews. The final 14 Wikipedia days reuse the Task 04 event-amplified
fixture. Agenda contains the specified sparse policy/campaign incidences with
every other canonical date/topic count explicitly zero. Two accepted
hypotheses collapse to one Synthetic Polling package ending 2026-08-22.
Coverage Anatomy is deliberately absent from the primary acceptance image.

Read-only named live smoke:

```powershell
python -B -m tools.fr27_trace.signal_braid --candidate-id edouard-philippe
```

Frozen visual smoke:

```powershell
python -B -m tools.fr27_trace.render `
  --fixture tools/fr27_trace/fixtures/signal_braid_candidate_v1.json `
  --output _trace_output/task-05-candidate-trace.png
```

Explicit-candidate live visual smoke:

```powershell
python -B -m tools.fr27_trace.render `
  --candidate-id edouard-philippe `
  --output _trace_output/task-05-candidate-trace-live.png
```

Both render paths run a headless DOM geometry audit before capture. For Signal
Braid the audit rejects clipped or overlapping topic labels, marks outside their
topic/date cell, collapsed simultaneous topics, and any Agenda date-grid x
coordinate that disagrees with the quantitative lanes or poll plot.

The PNG is an ignored local runtime artifact. Normal extraction remains
read-only and no production JSON is mutated.
