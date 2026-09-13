# Task 04 — Flash/Shift Prototype

Task 04 adds one bounded temporal instrument inside the existing public
Candidate TRACE family:

```text
validated candidate_attention.json (read only)
-> explicit canonical candidate ID
-> final two complete seven-day windows
-> frozen production-classifier parity verification
-> eligible TRACE or valid suppression
-> Task 02 render model and shell
-> Flash/Shift TRACE FIELD
-> local 1280 x 720 PNG
```

The detector ID is `flash_shift.v1`. `flash_shift` is only an internal field
renderer discriminator; it is not a sixth public family.

## Authoritative source and validation

The only live authority is repository-root `candidate_attention.json`, current
schema 1.1. The convenience adapter fixes that path and requires an explicit
canonical candidate ID. It performs no fuzzy lookup, ranking, fallback,
network request, writer call, rebuild, or production mutation.

The adapter reuses `candidate_attention_contract.validate_candidate_attention`,
whose import is side-effect-free. That production contract validates the
locked source and methodology, 90-day period and exact daily sequence, integer
view observations, weekly and 28-day sums and changes, earliest-date peak tie
behavior, peak share, peak-removed comparison, and allowed interpretation
flags. It does not prove that an allowed flag is the classifier result.

`flash_shift.py` therefore has one small parity function. It copies the exact
current production constants and classifier precedence without importing
`build_candidate_attention.py` at runtime:

1. latest seven-day views below `3000` -> `low_base`;
2. unavailable raw or peak-removed comparison -> `stable`;
3. evaluate event amplification with raw absolute change at least `10.0`, and
   the production sign-removal, 15-point-difference/0.40-retained-ratio, or
   0.35-peak-share/collapsed-adjusted-change rules;
4. raw and peak-removed changes both at least `+5.0` -> `sustained_rise`;
5. both at most `-5.0` -> `sustained_decline`;
6. otherwise -> `stable`.

Percentage change is `None` when the previous value is zero and otherwise
`round(((current - previous) / previous) * 100.0, 1)`. Each window removes its
own earliest tie-resolved peak for the adjusted comparison. Peak share is
`None` for a zero latest total and otherwise rounded to four decimals.

The semantics above are frozen for `flash_shift.v1`. A material upstream
classifier change must become visible in parity tests and requires deliberate
review/versioning; it must not silently alter this detector.

## Eligibility and suppression

Only these upstream flags are eligible:

- `event_amplified` -> `FLASH`;
- `sustained_rise` -> `SHIFT · RISE`;
- `sustained_decline` -> `SHIFT · DECLINE`.

`stable`, `low_base`, and unavailable evidence return a valid suppression and
no TRACE. A suppressed candidate is never replaced automatically. Missing,
malformed, arithmetically inconsistent, or classifier-inconsistent evidence is
a validation failure rather than suppression.

## Selected evidence and identity

The primary entity is the canonical candidate ID. The observation window is
exactly the previous-seven start through the latest-seven end: 14 complete,
adjacent UTC days. Identity-bearing evidence contains only:

- the stable `fr.wikipedia.org` / `pageviews` / `all-access` / `user` /
  `daily` source-method scope;
- the authoritative interpretation flag;
- both seven-day boundaries and all 14 exact daily pageview observations;
- previous and latest seven-day totals, raw change, latest peak date and value,
  latest peak share, and peak-removed change.

The shared Flash/Shift evidence validator recomputes every selected derived
value and the frozen classifier outcome. Candidate display name,
`generated_at`, the first 76 days, 28-day metrics, full-period peak, article
URL, other candidates, findings, qualifiers, language, renderer copy, and
cosmetic presentation are excluded from identity. Observed zero remains
distinct from unavailable comparison values.

## Visual semantics and limitations

Only the internal TRACE FIELD changes. Fourteen equal-spaced bars share one
legitimate quantitative scale because every bar is the same unit: daily
Wikipedia pageviews. Previous-window bars are muted, latest-window bars are
cyan, the seven-day boundary is explicit, and the latest-window peak receives
only a restrained amber exception marker. Exact dates, daily values, both
period ranges, five separate summary values, and the structural classifier tag
remain recoverable. There is no event-red, event T0, causal claim, composite
score, or political direction claim.

The footer states `FR27 WIKIPEDIA ATTENTION` and
`PAGEVIEWS ≠ SUPPORT OR SENTIMENT`. Pageviews do not establish unique people,
sentiment, approval, electoral support, or voting intention.

The frozen fixture uses seven prior values of 1,000 and latest values of 600,
600, 600, 5,000, 600, 600, 600. Exact production arithmetic yields 7,000,
8,600, +22.9%, a 5,000 peak and 0.5814 peak share, and -40.0% after each
window's peak is removed; the verified flag is `event_amplified`.

## Explicit commands

Read-only named live extraction:

```powershell
python -B -m tools.fr27_trace.flash_shift --candidate-id edouard-philippe
```

Frozen visual smoke:

```powershell
python -B -m tools.fr27_trace.render `
  --fixture tools/fr27_trace/fixtures/flash_shift_candidate_v1.json `
  --output _trace_output/task-04-flash-shift.png
```

Ordinary tests do not call Wikimedia or launch Chromium. The PNG is an ignored
local runtime artifact beneath `_trace_output/`.
