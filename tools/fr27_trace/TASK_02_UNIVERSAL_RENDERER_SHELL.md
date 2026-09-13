# Task 02 — Universal Renderer Shell

Task 02 adds the smallest isolated rendering surface needed to prove this flow:

```text
validated TRACE object
+ presentation-only render model
-> fixed universal TRACE shell
-> deterministic local 1280 x 720 PNG
```

Task 01 identity is unchanged. The frozen fixture contains a valid Task 01
draft under `trace` and separate non-identity copy under `presentation`.
Changing language, labels, finding copy, source scope, methodological boundary,
observation-window display text, or renderer version does not alter
`evidence_snapshot_hash` or `trace_key`.

## Architecture

- `render/model.py` validates both layers and maps the five frozen family codes
  to their public uppercase labels.
- `render/paths.py` permits fixture reads only below the TRACE fixture directory
  and PNG output only below repository-root `_trace_output/`.
- `render/shell.html`, `render/shell.css`, and `render/shell.js` define a fixed,
  network-free 1280 x 720 rendering surface. The TRACE FIELD is deliberately a
  neutral six-lane geometry preview with no detector or family semantics.
- `render/capture.cjs` launches Playwright only from an explicit command, blocks
  requests, waits for local fonts, validates viewport/canvas geometry, captures
  one PNG, and validates its PNG header dimensions.
- `render/cli.py` validates the fixture before invoking the capture process and
  passes only the presentation payload over standard input.

The universal frame, header, finding region, field bounds, footer, typography,
palette, and rhythm are frozen here. Later family work may change only the
internal TRACE FIELD geometry.

## Bounded shell refinement

The footer-right signature zone may contain one small standalone signal glyph
immediately before `france2027.app`. The mark is an inline arc-and-dot glyph
only: it has no app-icon container, badge, wordmark, gradient, or evidence
color. It remains confined to the existing 20% footer zone.

The TRACE FIELD keeps its exact bounds but uses no inner background, border, or
corner radius, so its neutral guides sit directly on the instrument surface.
Its temporal labels are the family-neutral `WINDOW START` and `WINDOW END`.
The entity/context label uses structural muted text rather than evidence cyan.

Footer source and methodological text remains 9px/600. The URL signature is
11px/700, modestly larger while remaining subordinate to the finding.

## Local setup and explicit smoke render

From repository root:

```powershell
npm install --prefix tools/fr27_trace
npx --prefix tools/fr27_trace playwright install chromium
python -B -m tools.fr27_trace.render `
  --fixture tools/fr27_trace/fixtures/render_shell_candidate_v1.json `
  --output _trace_output/task-02-universal-renderer-shell.png
```

No directory, browser, file, or network operation occurs on Python module
import. The capture command creates output directories only after the fixture
and output path have validated.

## Tests

The ordinary suite is Python-only and does not launch Chromium:

```powershell
python -B -m unittest discover -s tools/fr27_trace/tests -v
```

The explicit command above is the separate PNG smoke test. Generated output and
TRACE-local `node_modules` are ignored and must not be committed.

## Explicit exclusions

This milestone contains no real Candidate, Coverage Anatomy, Flash/Shift,
Field, Issue, Story, or Event visualization; detector; live FR27 dataset access;
automatic finding generation; public serial registry; archive; website
integration; X integration; publication automation; video; animation; workflow;
or scheduler.
