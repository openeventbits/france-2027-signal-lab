# FR27 responsive forensic harness

This directory contains audit/test tooling only. It reads the FR27 product sources and loads the existing dashboard in Chromium; it does not rewrite product CSS, JavaScript, markup, data, or responsive state.

## Setup

From `tools/responsive-forensics`:

```powershell
npm ci
npx playwright install chromium
```

The only package dependency is `@playwright/test`. Generated material is written to the ignored `artifacts/` directory.

## Commands

Static ownership inventory (JSON plus concise Markdown):

```powershell
npm run inventory
```

Source-derived viewport matrix (every integer source boundary at B-1/B/B+1, stable anchors, and representative short-height probes):

```powershell
npm run matrix
```

Full forensic sweep across all registered components and generated widths:

```powershell
npm run audit
```

Audits default to French, the canonical public locale (`/`). Select French, English (`/?lang=en`), or both explicitly:

```powershell
npm run audit -- --locale fr
npm run audit -- --locale en
npm run audit -- --locale fr,en
```

One component across the generated matrix:

```powershell
npm run audit -- --component masthead
```

Several components or a deliberately small width set:

```powershell
npm run audit -- --component masthead,what-changed,race,events --widths 1024,1023,761,760,720,719,700,699
```

Locale selection composes with component, width, height, localization-interval, CDP, and screenshot controls:

```powershell
npm run audit -- --component masthead --locale fr,en --widths 1024,1023,700,699,430,320
```

Only `fr` and `en` are supported. Unsupported values fail before a browser is launched, and selecting one locale never silently runs the other.

Constrained-height audit:

```powershell
npm run audit -- --component footer,what-changed --widths 1023,760,430 --height 600
```

Pixel-by-pixel transition localization within a bounded interval (maximum 250px):

```powershell
npm run audit -- --component masthead --localize 690:730
```

Behavioral responsive tests, including delayed Media Pulse state persistence:

```powershell
npm run test:behavior
```

This also exercises the production language links from canonical French to English and back, verifies URL/document/runtime/`aria-current` state after navigation and a Tier 3 resize, and proves that the real `#signal-events` workspace hash survives both language switches.

Selective, unapproved screenshot evidence:

```powershell
npm run screenshots
```

The screenshot command captures only Masthead evidence for FR + EN at 1023px and 699px. Names include locale (for example `masthead-fr-1023x900.png`). It does not create or update Playwright golden baselines. To capture a different small set, add `--screenshots` to any audit command, for example:

```powershell
npm run audit -- --component masthead --locale en --widths 1023 --screenshots
```

Run all harness tests:

```powershell
npm test
```

## Architecture

- `src/inventory.mjs` scans external stylesheets/scripts and inline HTML style/script blocks. CSS entries retain at-rule type, condition, inclusive/exclusive range semantics, source line, thresholds, and governed selectors. JavaScript entries identify media queries, width reads, listeners, observers, responsive class/state operations, DOM relocation, and restoration-like controllers.
- `src/matrix.mjs` derives probes from the inventory, constrains them to widths of at least 320 CSS pixels, and adds architectural anchors and three short-height configurations.
- `src/locales.mjs` defines the supported audit locales, canonical/default French behavior, and English entry URL without duplicating locale-independent inventory or matrix work.
- `src/registry.mjs` maps the twelve logical components to stable existing selectors, useful sub-probes, workspace hashes, and explicitly required controls.
- `src/server.mjs` is a dependency-free local static server used only by the harness.
- `src/forensics.mjs` captures rectangles, text-line estimates, computed layout properties, scroll geometry, viewport/clipping state, active/current state, tier classes, selected state, required-control availability, requested/resolved locale evidence, page overflow, and console exceptions. Approved dense analytical scrollers are identified separately from document-level overflow.
- `src/audit.mjs` sweeps widths in descending order inside each requested locale, builds compact signatures, flags same-locale abrupt transitions for human review, correlates them with source boundaries, and optionally enriches changes with matched-rule data from Chrome DevTools Protocol. When both locales run, it separately compares FR and EN at the same component and viewport.
- `tests/media-pulse.spec.mjs` demonstrates retrying state-persistence assertions after settling and after a Tier 2 → Tier 3 transition.
- `tests/screenshots.spec.mjs` demonstrates evidence capture without approving visual baselines.

## Reports

- `artifacts/responsive-ownership.json`: machine-readable source inventory.
- `artifacts/responsive-ownership.md`: inventory summary.
- `artifacts/viewport-matrix.json`: generated widths, short-height probes, and boundary-to-source mapping.
- `artifacts/responsive-audit.json`: raw browser measurements, signatures, hard findings, transitions, source candidates, and CDP matched rules.
- `artifacts/responsive-audit.md`: concise component-oriented review report.
- `artifacts/screenshots/`: selective evidence images only.

`REVIEW` is intentionally not synonymous with failure. A responsive structural change inside one locale, or a cross-locale difference in component/probe dimensions, line count, structure, scroll geometry, or control availability, needs human classification. French being wider or taller is not itself a failure. Source correlation and CDP matched rules are diagnostic candidates and cannot always prove cascade causality, especially with custom properties, inheritance, JavaScript-written inline state, container queries, or several same-specificity rules.

The objective hard checks cover requested-locale resolution, page-level horizontal overflow, declared required-control loss/disablement, Masthead language-control viewport/clipping violations, responsive tier overlap, and browser console/page exceptions. Locale resolution requires agreement between the requested locale, URL representation, `<html lang>`, `FR27I18N.locale`, and the single active language link. Local overflow is recorded but is not automatically failed; known analytical matrix/history scrollers are labeled `approved-local`. Additional component-specific invariants should be declared in the registry only after a human defines the intended contract.
