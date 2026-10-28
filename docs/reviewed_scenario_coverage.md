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

The historical public assessment API authenticates the shipped manifest and pin,
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

## Phase 1 current review: notice 10333 only

Select the independent current review explicitly:

```sh
python -B reviewed_scenario_coverage.py --review 10333-20261028 \
  --evidence-dir /external/fr27-audit/evidence
```

Only `10333.pdf` is required for this review. The assessment reads the current
checkout's tracked documentary records, route registration and actual French
and English HTML files. It neither downloads evidence nor rebuilds publication.
JSON goes to stdout; redirect it outside the repository if a saved report is
needed. `--corpus-dir` selects only the two numerical data files, never review
pins, code dependencies or publication evidence. There are no bypass flags,
caller-supplied event arrays or automatic repinning commands.

The new overlay is `fr27_commission_scenario_coverage_review_20261028.json`,
schema `fr27-commission-scenario-coverage-review/1`, review
`FR27-COMMISSION-SCENARIO-10333-20261028`. Its canonical SHA-256 is independently
pinned in the diagnostic. The overlay authenticates:

- Baseline `9637403e40a8a77bb1031faafad5d291b3993830`, with all 349 first-round
  and 108 runoff objects, hashed in full and sorted by immutable event ID.
- The unchanged historical manifest and pin, the exact 10333 survey and
  Commission registry identity, and the original PDF hash
  `cfe91916d69dc57bb57aa4979f09d00430bd25983a0ee77d087a0cab7020df94`.
- The complete four-scenario inventory, published columns, pages, candidate
  configurations, literal rows, respondent bases, existing event bindings and
  source provenance. Event IDs are reused, never generated.
- Current source hashes for the five existing identity-code dependencies,
  independently of the historical code attestation.
- The authenticated source-table collection and individual 10333 record,
  registered bilingual route association, and both complete HTML pages.
  Publication checks also inspect language, canonical URL, all 13 displayed
  names/literals, documentary state labels, card identity and original PDF link.

Code and HTML hashes normalize CRLF to LF for portable checkouts. JSON hashes
use canonical JSON; numerical array order and wrapper timestamps do not affect
identity. Whole-event changes, including metadata, do. Unrelated corpus additions
also make this finite current review stale. A new review is required rather than
silently extending its scope or refreshing its digest. These pins establish
review integrity, not a digital signature from the Commission.

The current implementation is private and reached through the explicit CLI
selector. The historical `assess_coverage(evidence_dir, *, corpus_dir=None)` API,
wildcard exports, default CLI selection, original manifest and original pin are
unchanged. The old 346-object diagnostic is not repinned. On this current
baseline it still refuses its changed `fetch_polls.py` dependency; its original
346/108 corpus attestation also differs from current production. A later Git
commit alone does not invalidate either assessment if authenticated inputs agree.

### Independent dimensions and unknown evidence

Each scenario reports separate dimensions:

| Dimension | States and meaning |
|---|---|
| Source authentication | `verified`, `unavailable`, `changed`: original PDF bytes against the reviewed identity |
| Numerical coverage | `verified`, `absent`, `conflicting`, `unverified`: faithful exact numerical representation, independently of documentary publication |
| Documentary coverage | `published`, `reviewed-only`, `absent`, `unverified`: actual FR27 documentary publication versus reviewed source evidence only |

An unavailable/changed PDF does not erase independently authenticated documentary
publication, but all numerical states become `unverified`; no numerical absence
or completeness claim is made. A missing/changed documentary input makes the
first-round documentary and numerical dimensions `unverified`, while correctly
authenticated runoffs can remain numerically verified. A missing published route
is not proof of confirmed documentary absence. `absent` documentary coverage is
reserved for reviewed evidence of absence; this finite review emits `published`
for the first round and `reviewed-only` for its three runoffs.

Invalid core authentication (overlay, manifest, notice identity, dependencies or
complete corpus) refuses assessment with exit 2 and no scenario/summary claims.
Missing/changed PDFs or publication inputs return `REVIEW_REQUIRED`, exit 2,
independent scenario states and `null` for aggregate completeness/absence counts
that cannot be established. Stale corpora return `BASELINE_STALE`. No failure
clears a registry warning or changes production data.

### Authenticated reference result

With real evidence authenticated, exit 0 / `ASSESSED` means this finite review
was assessed successfully. It does **not** mean numerical completeness.

| Stable scenario ID | PDF / expressed base | Numerical coverage | Documentary coverage |
|---|---|---|---|
| `10333-first_round-p12-1` | p.12 / 680 | `absent`, reason `non_exact_source_values` | `published` |
| `10333-second_round-p13-1` | p.13 / 518 | `verified`, Mélenchon 31 / Le Pen 69 | `reviewed-only` |
| `10333-second_round-p14-1` | p.14 / 574 | `verified`, Philippe 44 / Le Pen 56 | `reviewed-only` |
| `10333-second_round-p15-1` | p.15 / 603 | `verified`, Glucksmann 44 / Le Pen 56 | `reviewed-only` |

The summary is four expected configurations, three verified numerical runoffs,
one published documentary-only first round, zero configurations without either
representation, one without faithful numerical representation, and
`numerically_complete: false`. The registry remains `unresolved`.

All scenarios separately retain 1,033 adults, 973 registered voters, 731 certain
voters and their scenario-specific expressed bases. Existing runoff objects
retain their 973-person reported sample representation. The original `<1%`
bounds for Arthaud and Bouamrane carry `upper_percent`, never an exact `percent`.
The other candidate percentages summing to 100 does not authorize dropping or
coercing either bounded row.

### Validation and the older production-count assertion

The original 49 historical tests remain unchanged. Additional controlled tests
exercise current authentication, documentary publication, missing/changed inputs,
source/score/lineup/base conflicts, duplicate assignments, both bound coercion
and removal, deterministic output, offline operation and absence of writes/IDs.
Their synthetic document bytes and independently anchored synthetic corpora
test behavior; they are not proof of authentication against real evidence. Run
the CLI separately with the original PDF and tracked publication inputs to
establish the actual current result.

`test_commission_notice_coverage.CurrentCommissionCoverageRegressionTests.
test_audited_production_contains_454_observations` still expects 346 + 108,
whereas this baseline has 349 + 108. It is outside this four-file change.
Simply replacing 454 with 457 would only refresh a count. A separately reviewed
repair should authenticate the original 346/108 IDs and full objects as a
preserved subset, reject changed/missing historical objects and duplicate IDs,
and permit separately reviewed additions. A current-count assertion can be
additional evidence, but cannot substitute for historical preservation.

The existing reconciliation integration tests also contain stale snapshots:
the cached CLI assertion expects 42 relevant notices / 34 reconciled, whereas
the tracked registry now has 43 / 35, and the unrelated-notice digest predates
subsequent registry additions. Their event-object equality checks still pass.
These assertions likewise need a separate review rather than changes here.

No ingestion, registry, public-page, production-workflow or deployment entry
point imports or runs this current review. Notices 10319, 10327, 10260 and 10264
remain outside its scope and require their own explicit reviews.
