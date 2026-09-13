# FR27 TRACE Implementation Boundaries

## Purpose

FR27 TRACE is a local content-production tool.

It reads validated FR27 evidence and produces local TRACE artifacts for manual publication.

TRACE is NOT part of the FR27 website, deployment surface, production-data pipeline, or GitHub Actions system.

Conceptual flow:

validated FR27 data
-> deterministic TRACE detector
-> TRACE object
-> local renderer
-> PNG / MP4 / caption output
-> manual publication

## Allowed write scope

Implementation work may modify only:

- tools/fr27_trace/**
- .gitignore, only for TRACE-local ignored output/dependency paths

Generated runtime output must exist only beneath:

- _trace_output/**

## Read-only FR27 inputs

TRACE may read existing validated FR27 data required for evidence extraction.

Production datasets are inputs only.

TRACE must not rewrite, normalize, promote, refresh, patch, or otherwise mutate FR27 production data.

## Forbidden modifications

TRACE implementation must not modify:

- index.html
- en/**
- fr/**
- assets/**
- .github/**
- root production JSON datasets
- existing production builders
- existing production workflows
- existing FR27 publication/deployment code

No website route, dashboard panel, TRACE archive, Pages integration, X API integration, scheduler, or automatic posting is part of v1.

## Output-root invariant

All generated TRACE artifacts must resolve beneath the repository-local `_trace_output/` directory.

Any requested or computed output path that resolves outside `_trace_output/` must fail closed.

TRACE must not accept arbitrary production-file destinations.

## No import-time side effects

Importing any module under `tools.fr27_trace` must not:

- write files
- create directories
- launch a browser
- execute Playwright
- fetch network resources
- mutate production data
- update registries
- generate TRACE artifacts

State-changing work may occur only from an explicit build/render entry point.

## Fixture-first development

The first implementation must use frozen fixtures.

Do not connect detectors or rendering logic to live FR27 datasets until:

1. the TRACE object contract is implemented;
2. deterministic identity tests pass;
3. fixture-based validation passes;
4. repo-isolation tests exist.

## Real-data integration

When live FR27 datasets are introduced, access is read-only.

A real-data integration run must leave all tracked FR27 production files unchanged.

Only `_trace_output/` may change as a consequence of a TRACE build.

## Repository-isolation regression test

Tests must establish the invariant:

run TRACE
-> protected FR27 files remain unchanged
-> only permitted TRACE-local output may be created

## Dependency isolation

TRACE-specific runtime dependencies should remain inside `tools/fr27_trace/` wherever practical.

Do not modify FR27 frontend dependencies merely to support TRACE rendering.

Do not invoke production writer modules.

Pure existing FR27 functions may be reused only when they are demonstrably side-effect free.

## Evidence semantics

TRACE represents existing validated FR27 evidence.

It must not invent political interpretations, causal claims, momentum scores, forecasts, or composite political scores.

Detector output must remain deterministic and grounded in explicit evidence contracts.

Missing, zero, not observed, unavailable, and not applicable must remain distinct states.

## TRACE identity

TRACE identity must derive from the selected evidence slice, not from unrelated changes elsewhere in an upstream dataset.

Re-rendering the same evidence must preserve the same deterministic TRACE identity.

Language, rendering format, generated timestamp, and cosmetic renderer changes must not create a new evidence identity.

## Version 1 exclusions

The following are explicitly out of scope:

- FR27 website integration
- GitHub Actions automation
- automatic X publishing
- X API credentials or posting logic
- production-data writers
- automatic deployment
- scheduled TRACE generation
- public TRACE archive
- autonomous editorial ranking across families

## Codex operating rule

Before implementation is accepted, Codex must report:

- `git status --short`
- `git diff --name-only`

Any changed path outside the allowed write scope must be treated as a failed implementation and reverted before proceeding.

Do not use `git add .`.

Stage only explicitly reviewed TRACE files.

## First implementation scope

The first Codex task is limited to:

- TRACE v1 data contract
- deterministic evidence canonicalization
- deterministic TRACE identity
- frozen fixtures
- unit tests
- repository-isolation tests

Do not implement detectors, renderer, Playwright capture, live-data integration, registry mutation, or publication logic in the first task.
