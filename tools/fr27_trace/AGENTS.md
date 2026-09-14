# FR27 TRACE Codex Instructions

Read `IMPLEMENTATION_BOUNDARIES.md` in this directory before making any change. It is the authoritative implementation and safety contract.

## Scope

Work only inside `tools/fr27_trace/**` unless the user explicitly authorizes a specific exception.

Do not modify the FR27 website, production datasets, assets, workflows, production builders, or deployment code.

FR27 production data is read-only input.

All generated runtime artifacts must remain beneath repository-root `_trace_output/`.

## Engineering rules

Prefer the smallest deterministic solution that satisfies the approved TRACE contract.

Do not add frameworks, services, databases, network dependencies, automation, or abstractions unless they are required by the current bounded task.

Do not invent political interpretation, causal claims, forecasts, momentum measures, or composite scores.

Do not perform file writes, browser launches, network access, or other state changes at module import time.

Use frozen fixtures before live FR27 data.

## Git rules

Do not create branches, commit, push, stage files, or use `git add .` unless the user explicitly asks.

Before finishing any task, run and report:

- `git status --short`
- `git diff --name-only`

If any path outside the authorized write scope changed, stop and report it rather than proceeding.

## Current task boundary

Task 01 is complete and frozen. Its historical boundary remains:

- TRACE v1 data contract
- deterministic evidence canonicalization
- deterministic TRACE identity
- frozen fixtures
- tests, including repository-isolation tests

Task 02 expands the current boundary only to:

- a presentation-only render model outside TRACE evidence and identity
- a fixed 1280 x 720 universal TRACE shell
- a neutral TRACE FIELD geometry placeholder
- one frozen synthetic Candidate-family shell fixture
- explicit local Playwright/Chromium PNG capture
- fail-closed output paths beneath repository-root `_trace_output/`
- renderer-focused tests and task documentation

Task 02 shell geometry, branding, typography, palette, and all regions outside
the TRACE FIELD are complete and frozen.

Task 03 expands the current boundary only to:

- one frozen synthetic Coverage Anatomy fixture;
- detector identity `coverage_anatomy.v1` inside public family `candidate`;
- one explicit-candidate, read-only adapter for
  `news_wire.json:candidate_visibility`;
- one `coverage_anatomy` field payload and field renderer inside the frozen
  Task 02 shell;
- one ignored local `_trace_output/task-03-coverage-anatomy.png` smoke artifact;
- focused extractor, identity, renderer, and isolation tests;
- Task 03 documentation.

Do not change the Task 01 identity model or any Task 02 shell geometry outside
the TRACE FIELD. Do not create a Coverage Anatomy public family. Do not add
candidate ranking, publication thresholds, automatic findings, production
writes, registry mutation, website integration, publication logic, animation,
workflows, or scheduling.

Task 04 expands the current boundary only to:

- one frozen synthetic Flash/Shift event-amplified fixture;
- detector identity `flash_shift.v1` inside public family `candidate`;
- one explicit-candidate, read-only adapter for schema-1.1
  `candidate_attention.json`;
- reuse of the side-effect-free production artifact validator plus one
  TRACE-local frozen parity guard for the existing production classifier;
- an exact final-14-day evidence slice and eligible-or-suppressed result;
- one `flash_shift` field payload and field renderer inside the frozen Task 02
  shell;
- one ignored local `_trace_output/task-04-flash-shift.png` smoke artifact;
- focused classifier, extraction, identity, renderer, and isolation tests;
- Task 04 documentation.

Flash/Shift is not a public family and must not import the production builder
at runtime. It must not call Wikimedia, accept an arbitrary live source path,
fall back to `candidate_signals.json`, select or rank candidates, invent
thresholds, generate political prose, imply causal events, or treat pageviews
as support, sentiment, approval, unique people, or voting intention. Stable,
low-base, and unavailable records are valid suppressions; malformed evidence
fails closed. A material production classifier change requires deliberate
review and detector versioning rather than a silent `flash_shift.v1` change.

Task 05 expands the current boundary only to:

- one frozen synthetic Signal Braid fixture;
- detector identity `signal_braid.v1` inside public family `candidate`;
- exactly four visible lanes: Media, Wikipedia, Agenda / Issues, and Poll Tests;
- an exact 28-complete-UTC-day common window selected from validated fixed
  production artifacts for one explicit canonical candidate ID;
- a deterministic composition requiring two fully observed longitudinal lanes
  and either a contained eligible Task 04 child or an accepted first-round poll
  package ending in the parent window;
- narrow selected child references for Task 04 and compatible Task 03 traces;
- one `signal_braid` field payload and renderer inside the frozen Task 02 shell;
- one ignored local `_trace_output/task-05-candidate-trace.png` smoke artifact;
- focused extraction, suppression, child compatibility, identity, renderer,
  isolation, and live-smoke tests; and
- Task 05 documentation.

Media and Agenda share candidate-linked news evidence. They are distinct
observable lanes, not independent corroborating sources. Lanes share time but
not units and are never mathematically combined. Do not add a score,
correlation, ranking, trend, momentum measure, causal connector, political
interpretation, party/candidate color, event-red styling, polling performance,
status, events, scrutiny, General Visibility, or another media scope. Task 05
must not import `build_candidate_signals.py`, accept arbitrary live source
paths, write production data, or auto-select a candidate.
