# Task 01 — TRACE v1 Contract and Identity

Read `AGENTS.md` and `IMPLEMENTATION_BOUNDARIES.md` completely before making any change.

Implement only the first bounded TRACE engineering milestone.

## Required implementation

Create the smallest maintainable Python implementation for:

1. TRACE v1 object validation.
2. Deterministic canonicalization of selected evidence.
3. Deterministic `evidence_snapshot_hash`.
4. Deterministic `trace_key`.
5. Frozen valid and invalid fixtures.
6. Unit tests for the contract and identity rules.
7. Repository-isolation tests appropriate to this bounded milestone.

## Frozen semantic rules

Valid public families are exactly:

- candidate
- field
- issue
- story
- event

TRACE identity must derive from:

- trace_schema_version
- family
- detector_id
- canonical primary entity IDs
- canonical observation window
- evidence_snapshot_hash

The selected evidence slice determines `evidence_snapshot_hash`.

Do not hash an entire upstream FR27 dataset merely because the selected evidence came from it.

The same semantic evidence must preserve identity despite:

- JSON object key order changes
- FR versus EN rendering choice
- generated timestamp changes
- cosmetic renderer/version changes
- unrelated changes elsewhere in an upstream dataset

Identity must change when:

- selected evidence changes materially
- observation window changes
- detector identity/version changes
- primary entity identity changes
- TRACE schema version changes

Evidence availability states must distinguish at least:

- observed
- not_observed
- unavailable
- not_applicable

Within `evidence`, the key `availability` is reserved for TRACE availability
records. Any mapping containing that key is an availability record and must
obey the availability-state rules, including when nested in objects or arrays.

An observed numeric zero must remain distinct from unavailable or not observed.

Identity-bearing evidence must contain stable semantic values or codes, not
FR/EN rendering copy or other presentation-only prose.

Draft TRACE objects have no public serial.

Do not implement public serial allocation or registry mutation in this task.

## Implementation constraints

Prefer Python standard library only unless a dependency is genuinely necessary.

Do not introduce Pydantic, JSON Schema tooling, databases, services, frameworks, or build systems merely for convenience.

Do not implement:

- detectors
- rendering
- HTML/CSS/JS
- Playwright
- live FR27 data access
- registry mutation
- publication
- X integration
- website integration
- GitHub Actions

Keep all implementation and tests beneath this directory.

Do not modify `.gitignore` in this task.

Do not commit, stage, push, or create branches.

## Acceptance tests

At minimum, tests must establish:

- same evidence produces same `trace_key`
- reordered JSON keys produce same `trace_key`
- language choice does not affect identity
- generated timestamp does not affect identity
- unrelated upstream provenance changes do not affect identity
- selected evidence change produces a new identity
- observation-window change produces a new identity
- detector version/change produces a new identity
- invalid family is rejected
- draft TRACE has no public serial
- observed zero remains distinguishable from unavailable
- malformed availability state is rejected
- importing TRACE modules produces no filesystem side effects

Before finishing:

1. run the TRACE test suite;
2. run `git status --short`;
3. run `git diff --name-only`;
4. confirm that every changed path is beneath `tools/fr27_trace/**`;
5. summarize implementation decisions and any unresolved questions.

Do not expand scope.
