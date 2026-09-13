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

Do not change the Task 01 identity model. Do not implement detectors, family
visualizations, live-data integration, registry mutation, website integration,
publication logic, animation, workflows, or scheduling.
