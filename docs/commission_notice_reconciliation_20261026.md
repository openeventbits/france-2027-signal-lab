# Commission notice reconciliation — 26 October 2026

Reviewed baseline: `04fa849466d2ec4ac487fe5d607d56c2db190601` (origin/main).
This correction changes coverage only for 10332, 10323 and 10319. It admits,
corrects and removes no numerical observations. All 346 first-round and 108
runoff objects, historical IDs, source tables, documentary pages and browsing
source scenarios remain unchanged.

## Evidence and decisions

`fr27_commission_reconciliation_review.json` is authenticated by a canonical
SHA-256 constant in `commission_notice_coverage.py`. It records the exact
notice identities, documentary evidence and finite reviewed relationships.
There is no fetching, automatic repinning, global institute alias or mandatory
commissioner rule. Original historical evidence bundles and their pins remain
unchanged. The manual historical scenario diagnostic is not a runtime input.

### 10332 — Toluna Harris Interactive for M6 & RTL

The authenticated 73-page Commission PDF has SHA-256
`62922752ec3c7a7e6e34504c312f57c52dc3621309897b311bfc52d8ebaeebd5`.
Fieldwork was 19–21 October, with 2,094 registered voters from 2,500 adults.
All five first-round configurations (pages 35, 37, 39, 42, 45) and three runoffs
(54, 57, 59), including all 61 candidate results, match exactly.

The review preserves the eight full event objects and their `Harris` labels,
null legacy commissioner/publication metadata and reported sample scope.
The Harris/Harris Interactive identity bridge is confined to this notice and
the authenticated study. Every event is required, including all runoffs;
missing, duplicate, extra, reidentified or modified objects fail closed.
Coverage is `reconciled / reviewed_10332_complete_configurations`, with all
eight event IDs. It is not an official parser claim.

### 10323 — YouGov for Le HuffPost

The current 29-page Commission notice has SHA-256
`8ed7e44d4db519c74672548bc8c107ccf4871cad2450d6416dc240faf9bde784`.
The 12-page YouGov results document has SHA-256
`2922415bdf4256360f206cb24466666b69596f1f2a109964694a7892e8baa89d`.
Both authenticate fieldwork 12–15 October, 1,094 adults including 976 registered
voters, all five first-round and six runoff configurations, and all 67 candidate
results. Compare Commission `Pondérés` with YouGov `Total`, including true zeros.
Expressed-voter bases remain separate from legacy adult sample representations.

The earlier Batch 2 identity used title spelling `YOUGOV`, download `/add/2340`
and PDF hash `4b2b38114f43bb35521323604842ca8266855c1ac6fd3cb2adc78df442aa9393`.
The current identity uses `Yougov`, `/add/2346` and the current hash above.
On review, `/add/2346` resolved to the current notice and `/add/2340` returned
404. The byte-level reason for the historical PDF change is unknown.

The Batch 2 matcher accepts either the original complete identity or exactly
the newly pinned complete variant. Mixed variants, metadata enrichment and
unreviewed title/link/hash changes still return `reviewed_notice_identity_mismatch`.
The historical identity being extended must itself match the pinned original.
All eleven objects must still equal the original Batch 2 snapshots. That bundle,
its SHA-256, historical fixtures and complete-collection safeguard are unchanged.
Coverage remains the established `reviewed_notice_complete_configurations_batch2`.

### 10319 — OpinionWay for CNEWS

The Commission PDF has SHA-256
`c66cc3da2bcdbf8cfcf5d93552242d8a20b09554eecee399be458e90282a079d`.
It publishes a 13-candidate first-round table on page 12, including Bouamrane's
literal `<1%`. Its context is 1,043 adults, 978 registered voters and 731 certain
voters. The expressed first-round base remains unverified. The exact subtotal
of 100 does not authorize conversion of `<1%` to zero.

The formerly matched event
`7c7bb3a59970c61e70ba91e474b2ed4a6386645d2b258b8d6c3aa9e4f7aecf03`
is PrésiTrack for Les Echos and Radio Classique, not CNEWS. The separate
PrésiTrack report's SHA-256 is
`dd8b43bf5fff0b09fecf3c385bc69a778fb305892987d5f34f57012ef010a42f`;
the corresponding Commission notice is 10318. Both same-window first-round
observations belong to that other source. Shared dates and apparent respondents
do not merge commissioners or candidate configurations.

The date-only nested survey metadata previously hid the top-level commissioner.
Two PrésiTrack configurations collapsed into one wave; `_corroborate_waves()`
accepts a single wave without optional corroboration and ignores optional
constraints with no matches. Removing that shortcut alone would not fix this.

The exact reviewed CNEWS decision runs before direct-ID and generic wave
inference, so no single wave, metadata enrichment or claimed `official_notice_id`
can clear it. Changed notice evidence remains unresolved for identity review.
Coverage is `unresolved / reviewed_cnews_incomplete_bounded_first_round`, with
no matched numerical IDs. The three authenticated CNEWS runoffs remain present.
The two documentary records for 10319 and 10333 retain their original IDs,
pins, literal bounds and `analysis_eligible=false` browsing projections.

## Integration and invariants

`fetch_polls.py` passes its unchanged filtered first-round evidence to ordinary
matching and supplies the complete two-round corpus separately through
`reviewed_events`. Existing generic and barometer matching retain their behavior.
The YouGov identity variant participates in the existing live Batch 2 layer;
frozen extraction and historical evidence remain independent.

| Notice | Before | After |
|---|---|---|
| 10332 | unresolved, pollster-label mismatch | reconciled, all eight exact objects |
| 10323 | unresolved, reviewed identity mismatch | reconciled, exact variant and eleven objects |
| 10319 | false reconciliation to PrésiTrack | unresolved, bounded first-round numerical gap |

Totals: 42 relevant notices; **3 parsed / 33 reconciled / 6 unresolved** become
**3 / 34 / 5**. The remaining unresolved IDs are 10333, 10327, 10319, 10264 and
10260, in registry order. All other 170 notice records, including their
classifications, matched IDs and methods, remain identical to the baseline.

A blanket same-URL-or-populated-commissioner requirement would demote 19
currently reconciled notices and is deliberately not introduced. No other
Harris study receives a new alias or coverage decision.

The original 439-object barometer review is selected explicitly through the
authenticated historical ID manifest, even when its test runs directly against
a later corpus. A separate production test checks 346 + 108 = 454 observations.
The frozen 439-, 437- and earlier baseline assertions, their fixtures and the
production contract runner remain unchanged.

The original cutover logic hashes and event-ID probes remain immutable.
`POST_CUTOVER_LOGIC_REVIEWS` records the new exact coverage-source hash and retains
the previous barometer review hash as history. It does not authorize arbitrary
future coverage changes.

Focused tests: `python -B -m unittest test_commission_reconciliation_review
test_commission_notice_coverage test_commission_coverage_batch2
test_reviewed_source_retention test_update_polls_contract_runner`.
Run the existing production contract runner for the historical composite review,
whose selected tests intentionally use the authenticated 439-object baseline.
Publication checks should render/check in memory or external temporary outputs;
this reconciliation does not regenerate documentary or numerical pages.
