# Reviewed historical scenario coverage diagnostic

This operator-invoked diagnostic assesses the five reviewed studies 10319,
10333, 10332, 10141 and 10166A. It imports nothing and changes no polling data,
registry state or publication output. No ingestion, builder, search, sitemap or
workflow entry point imports or executes it.

## Run manually

From the repository root, with an existing external cache and an external report
destination:

```sh
python -B reviewed_scenario_coverage.py \
  --evidence-dir /external/fr27-audit/evidence \
  > /external/fr27-review/scenario-coverage.json
```

In PowerShell, set `$ExternalEvidence` to the external cache directory and
`$ExternalReport` to a report path outside the repository, then run:

```powershell
python -B reviewed_scenario_coverage.py --evidence-dir $ExternalEvidence |
  Set-Content -LiteralPath $ExternalReport -Encoding utf8
```

The cache must contain the original reviewed `10319.pdf`, `10333.pdf`,
`10332.pdf`, `10141.pdf` and `10166a.pdf`. The diagnostic reads their bytes and
checks the pinned SHA-256 values; it neither downloads nor extracts PDFs. It
writes JSON only to stdout. `--corpus-dir DIRECTORY` can select a separate
directory containing both numerical JSON files; it cannot select code or review
pins. Python callers use `assess_coverage(evidence_dir, *, corpus_dir=None)`.

## Authentication and freshness

The only public assessment API authenticates the shipped manifest and pin,
original document bytes, complete numerical corpus, reviewed event bindings,
scoped institute aliases and respondent-base relationships. There is no public
assessment accepting event arrays, pre-authenticated states or bypass flags.
The code pins the canonical authentication record, which pins the manifest and
identity implementations. Changes require an explicit source/code review; no
repinning command is provided. These are review integrity controls, not digital
signatures or a substitute for the original table review.

The reviewed baseline is
`7b294e0bea0538980016e1bdc10e52bda9231397`: 346 first-round and 108 runoff
observations. The attestation hashes each entire event object, including its
immutable ID, sorted by ID in its round. Formatting, array order and runoff
wrapper metadata such as `generated_at` do not change numerical identity.
Additions, removals, changed IDs, sources, scores or event metadata make the
attestation stale. A stale corpus produces `BASELINE_STALE` with no scenario,
coverage or absence claims. A later unrelated repository commit alone does not
invalidate unchanged numerical objects. Identity helper changes also require
review; their source pins normalize line endings for cross-platform use.

Unavailable PDFs yield `UNVERIFIED`; changed bytes yield `REVIEW_REQUIRED` for
the affected study. Neither produces missing-data claims. Contradictory
commissioners, populations, bases, sources, complete candidate configurations or
exact vectors require review. An authenticated, scoped bridge explains missing
legacy metadata only for the unchanged reviewed object. Institute and fieldwork
alone never establish a match. Harris/Harris Interactive is scoped to 10332.

The manifest retains source-table result objects: `exact`/`percent`,
`strict_upper_bound`/`upper_percent`, and `source_dash` with unconfirmed numeric
meaning. All three authentic `<1%` rows remain literal bounds. Non-exact values
never verify an exact numerical vector, even when the exact subtotal is 100.
No score, numerical source, event ID or source-only card is corrected or added.

## Results and exit status

At the reviewed baseline the reference is 21 scenarios: 14 `NUMERIC_VERIFIED`,
six `MISSING_CONFIRMED`, one `MISATTRIBUTED`, and no confirmed missing runoff.
The seven absent faithful configurations are all first round; the misattributed
10141 configuration is counted once. Six CNEWS runoffs and all eight Harris
configurations are verified. 10319's PrésiTrack claim is rejected.

Numerical completeness, documentary evidence in the reviewed manifest,
documentary coverage already in FR27 and source-identity confidence are separate
fields. External evidence does not create a production source-only card.

Exit 0 means `ASSESSED`, including known confirmed gaps; inspect the JSON.
Exit 2 means review is required, evidence is unavailable or authentication is
invalid/stale. `CoverageDiagnosticError.code` identifies API-level refusal. The
diagnostic never affects a normal polling update, automatically replaces a
registry state, or triggers publication.

## Deterministic tests

```sh
python -B -m unittest -v test_reviewed_scenario_coverage
```

Tests construct synthetic corpora and document bytes in temporary directories,
with explicit test-only trust anchors. They do not depend on live polling JSON,
the external audit/PDF cache, network access or Git history. Reference IDs in
these controlled fixtures do not claim to reproduce historical object bytes.
The actual baseline and original PDFs are assessed only by the manual command.
No workflow changes are needed or included. The full Phase 1 ledger, PDFs,
local snapshots and preparation scripts are not repository inputs.
