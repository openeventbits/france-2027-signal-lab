# Task 03 — Coverage Anatomy Prototype

Task 03 is the first data-driven TRACE visualization. It adds one narrow
detector/component inside the existing public Candidate family:

```text
news_wire.json:candidate_visibility (read only)
-> explicit candidate selection
-> narrow comparable evidence slice
-> Task 01 draft TRACE object
-> Task 02 presentation model and universal shell
-> Coverage Anatomy TRACE FIELD
-> local 1280 x 720 PNG
```

The detector identity is `coverage_anatomy.v1`. `coverage_anatomy` is a field
renderer discriminator, not a sixth TRACE family or public brand. The header is
still `FR27 TRACE / CANDIDATE`. Coverage Anatomy remains a Candidate/Story
component; Task 03 implements only its Candidate use.

## Upstream source decision

The authoritative input is the existing
`news_wire.json:candidate_visibility` object because it contains both complete
seven-day periods, the upstream `comparison_quality` decision, and the
candidate-level structural measures used by the prototype.

`candidate_signals.json` is insufficient by itself: its per-candidate
`campaign_attention` object contains only the current structural profile, and
its top-level visibility summary does not contain the prior candidate metric
rows required for this comparison. `candidate_visibility_history.json` is an
archive with a different observation contract and is not used to reconstruct
the live pair. The adapter does not scrape articles, make network requests,
call builders, or fall back to either dataset.

The adapter imports only the demonstrably pure `candidate_identity.py` helpers
to map the upstream canonical candidate name to the FR27 canonical candidate
ID. That module performs no file, network, browser, or writer operation. The
candidate ID supplied to the adapter is mandatory; the adapter never ranks or
chooses a candidate.

## Exact selected upstream fields

The identity-bearing evidence selects only:

- `candidate_visibility.primary_scopes`, checked as the semantic set
  `campaign` plus `election` and stored in canonical order;
- from `prior_period` and `current_period`: `start_date` and `end_date`;
- from the explicitly selected row in each period's `candidate_metrics`:
  `record_count`, `share`, `publisher_count`, and `story_cluster_count`;
- from that row's `concentration`:
  `leading_publisher_record_count`, `leading_publisher_share`,
  `leading_story_record_count`, and `leading_story_share`;
- from `comparison_quality`: `status`, `reason`, current/prior total record and
  publisher counts, common and union publisher counts,
  `publisher_overlap_ratio`, `record_count_ratio`, and the five upstream gate
  thresholds.

The upstream `candidate` field is read to resolve the requested canonical ID.
Its canonical display name is returned separately for presentation and is not
the primary identity key or identity-bearing prose. The TRACE observation
window spans prior-period start through current-period end.

Every selected metric is an explicit TRACE `observed` availability record.
The adapter checks field presence separately from value validation, so numeric
zero remains observed and cannot collapse into missing or unavailable.

The following are deliberately excluded from selected evidence:

- complete `story_clusters` and story/item identifiers;
- `publisher_names` and `leading_publisher` display identity;
- active-day and headline/summary match diagnostics;
- scope counts and scope shares beyond the selected campaign/election scope;
- general-visibility periods;
- `candidate_watch`, articles, other candidates, top-level generation data,
  and unrelated news-wire fields;
- all `candidate_signals.json` and `candidate_visibility_history.json` values.

Consequently the evidence hash changes for a selected metric, period, scope,
or gate input, but not for unrelated news-wire content, candidate display
prose, findings, qualifiers, language, or renderer copy.

## Comparability and editorial boundary

The adapter requires the existing upstream
`comparison_quality.status == "comparable"`. Any other upstream status is a
hard suppression. The stored quality values and thresholds make that upstream
eligibility decision auditable, but Task 03 does not recompute or replace it
with a second comparability algorithm.

No autonomous publication threshold, significance score, ranking, top-N
selection, or generated finding is frozen here. A human must provide a
candidate ID. The frozen synthetic presentation uses the literal finding:

`COVERAGE STRUCTURE BECAME MORE CONCENTRATED.`

and the factual qualifier:

`Publisher and story breadth narrowed as leading shares increased.`

Those sentences belong only to the synthetic fixture and are never generated
for live candidates.

## Renderer boundary

The Task 02 1280 x 720 canvas, frame, header, finding region, TRACE FIELD
bounds, footer geometry, signature, typography, and palette remain unchanged.
Only the contents of the TRACE FIELD change when
`presentation.field_type` is `coverage_anatomy`.

The field has five independent-unit rows in this fixed order:

1. `COVERAGE SHARE`
2. `PUBLISHERS`
3. `STORY CLUSTERS`
4. `LARGEST STORY`
5. `TOP PUBLISHER`

It shows exact `PRIOR` and `CURRENT` values and both exact period ranges.
Prior values use structural muted color and current observed values use cyan.
Only the column header contains a temporal direction cue. The rows contain
paired exact values with no connectors, bars, shared scale, composite score,
party color, gradient, event red, or positive/negative judgment.

The footer source scope is `FR27 CANDIDATE-LINKED COVERAGE`; its boundary is
`COVERAGE STRUCTURE ≠ SUPPORT OR SENTIMENT`.

## Explicit commands

Read-only live extraction requires an explicit candidate ID and writes only to
standard output:

```powershell
python -B -m tools.fr27_trace.coverage_anatomy --candidate-id edouard-philippe
```

The frozen visual smoke is explicit and keeps output beneath the guarded
repository output root:

```powershell
python -B -m tools.fr27_trace.render `
  --fixture tools/fr27_trace/fixtures/coverage_anatomy_candidate_v1.json `
  --output _trace_output/task-03-coverage-anatomy.png
```

Ordinary Python tests do not require Chromium and do not read changing live
political values. The committed visual regression fixture is synthetic; the
PNG is a generated ignored runtime artifact and is not committed.
