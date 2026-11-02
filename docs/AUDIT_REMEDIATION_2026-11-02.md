# November 2 follow-up: evidence interpretation remediation

Implementation and verification record for the focused pull request. Merging, deployment and manual production workflow execution are outside this change's authorization.

- Repository: `openeventbits/france-2027-signal-lab`.
- Branch: `codex/fr27-audit-nov2`.
- Fresh isolated managed worktree based on the fetched `origin/main` revision.
- Fetched baseline: `24539cd1899532822d197702640e43657c5ee3c9`.
- Re-fetch for final review returned the same main revision; no synchronization or conflict resolution was needed.
- The untouched original checkout was preserved at the same baseline and used to reproduce the documented pre-existing failures.

## 1. Runoff spotlight date

**Reproduction and cause.** `closest_tested_runoff.json` selects the exact July 7–8, 2026 shared window, with Harris 49–51 and Ifop 46–54 for Philippe–Le Pen. Later observations exist in `second_round_polls.json`. The published desktop workspace hid each observation's date with `.hybrid-runoff-observation-head > span { display: none; }`; the responsive layout also hides the workspace's evidence header. Thus dates existed in the DOM and hover metadata but were absent beside the prominent comparison. A saved live desktop capture confirmed both date spans had `display: none`.

**Authority and consumers.** Raw second-round observations → `fetch_polls.derive_closest_tested_runoff` → `closest_tested_runoff.json` → the legacy spotlight in `index.html`, hybrid summary and `renderRunoffClosest` in `assets/hybrid-dashboard.js`. Existing coverage is in `test_runoff_workspace.py` and polling preservation contracts.

**Change and visible result.** Both locales now display the source window and say it is the latest qualifying shared-window comparison, not the latest runoff poll. The hybrid comparison reuses the former redundant narrowest-margin footer band for this context; the exact 2- and 8-point margins remain beside the observations. The legacy spotlight and summary also carry the qualification. Scoped CSS keeps the text wrapped and readable without covering the score rows.

**Files and regressions.** `index.html`, `en/index.html`, `assets/hybrid-dashboard.js`, `assets/hybrid-dashboard.css`, `assets/tier3-layout.css`, and both locale catalogs. The updated presentation assertion in `test_runoff_workspace.py` retains its source-score, margin, provenance and identity assertions. `test_audit_evidence_interpretation.py` checks the qualified window, and the browser regression checks visible dates, wrapping, and score/footer separation at four widths in FR/EN.

**Intentionally unchanged.** No qualifying-window, matchup-selection, event-ID, source or historical observation changed. The two historical observations were not replaced with newer non-comparable polls.

## 2. Cross-institute polling arrows

**Reproduction and cause.** The published Ipsos tab showed `▼ −1.5 pts†` against Harris for Marine Le Pen. The comparison classifier already distinguished `DIRECT`, `FIELD_CHANGED`, `POLLSTER_CHANGED`, and `POLLSTER_AND_FIELD_CHANGED`, but `formatRacePreviousPollDifference` assigned positive/negative/zero tones from the delta alone. `renderBars` then generated directional glyphs from those tones. Essential qualifications were in tooltip/ARIA text.

**Authority and consumers.** Exact first-round observations in `polls.json` and source study bindings → `deriveRacePreviousPollDifference` in `index.html` → all Race at a Glance poll tabs and scenario selections. Existing tests: `test_frontend_facts.py` and `test_race_glance_defaults.py`.

**Change and visible result.** Raw signed numerical differences and scores are unchanged. Non-direct comparisons use a neutral contextual tone with no up/down/approximately-equal glyph or dagger. Each row visibly identifies raw comparison context, including the preceding institute where relevant, or a candidate-field change. Direct comparisons remain distinctly labelled as the same institute and field. Missing and ambiguous priors retain em dashes and now have compact visible labels. Detailed source dates, scores, and added/removed candidates remain accessible in tooltips.

**Files and regressions.** Homepage source and generated English entrypoint, shared/tier-3 CSS, and bilingual catalogs. New functional tests cover all four comparison classes plus missing and ambiguous priors. Browser coverage exercises every homepage tab and scenario in FR/EN and checks neutral glyphs and visible qualifications. The tooltip explanation regression now describes the visible context accurately.

**Intentionally unchanged.** Prior-observation selection, ambiguity handling, candidate fields, source scores and arithmetic were preserved. No voter movement is inferred.

## 3. Media Pulse partial-day comparisons

**Reproduction and temporal contract.** At the retained generation timestamp `2026-11-02T02:39:41.026629Z`, both the news builder and browser fallback anchored the current seven-day window on November 2. The published comparison was October 27–November 2 against October 20–26. `candidate_signals.json` copied those boundaries into the active-field projection, which is the homepage comparison authority. Existing source-overlap/volume gates did not test calendar-day completeness. Candidate visibility history already excluded the current UTC day.

**Authority and consumers.** Retained publication timestamps and candidate associations → `fetch_news_wire.build_candidate_visibility` → `news_wire.json` → `build_candidate_signals.derive_active_field_visibility` and candidate visibility projections → homepage Media Pulse, candidate workspace, dossiers and visibility history. `build_search_entrypoints.py` renders the same runtime Media model for the static bilingual snapshot. Candidate attention provider data does not consume these news rows. Social media consumers were also checked.

**Change and visible result.** The default periods end on the day before generation in UTC: October 26–November 1 and October 19–25 for this snapshot. Python validation and the browser fallback agree. Empty complete days are retained; no day is skipped merely because it contains zero records. The unchanged generation timestamp remains an observation cutoff, not a new fetch claim. The real-time coverage reader still includes current-day articles; it does not contribute the default seven-day movement.

The visible disclosure reads “Complete seven-day UTC periods · article counts & bases” (localized in French). One click opens a native browser popover containing all six current/prior candidate numerators and active-field denominators, with the overlap explanation. It escapes chart-panel clipping and closes with Escape or an outside click. A focused idempotent-placement fix in `assets/tier2-layout.js` prevents its existing observer from unnecessarily reparenting an already placed Media panel, which would close the popover at narrow widths. An open popover is also preserved through data refresh. Thematic coverage explicitly labels its numbers as source-days, separately from article counts. Failed comparability gates retain their existing arithmetic/availability contract and use neutral raw-difference styling.

**Independent arithmetic.** Using unique source-record IDs linked to at least one active candidate, the bases are **379 current / 271 prior**. Shares below follow the existing three-decimal share rounding and subtraction contract; they are not poll measurements.

| Candidate | Current articles / base | Prior articles / base | Displayed shares | Difference |
|---|---:|---:|---|---:|
| Édouard Philippe | 90 / 379 | 21 / 271 | 23.7% / 7.7% | +16.0 pp |
| Gabriel Attal | 88 / 379 | 14 / 271 | 23.2% / 5.2% | +18.0 pp |
| Marine Le Pen | 64 / 379 | 110 / 271 | 16.9% / 40.6% | −23.7 pp |

The gate remains comparable: 48 common publishers out of 78 in the union, overlap 0.615 and record-count ratio 1.399. All gate thresholds are unchanged. The new independent regression recomputes every active candidate row from source records, including numerators, denominators, shares and available differences.

**Files and regressions.** `fetch_news_wire.py`, hybrid renderer/CSS, responsive controller and locale catalogs; current derived news, candidate signals, visibility/agenda history, affected FR/EN dossiers/hubs, live projection dependency revisions and publication manifest; bilingual homepage snapshots. Synthetic visibility fixtures now generate on the following UTC day so their original period contents and gate-boundary assertions remain intact. New tests cover midnight, late-day and timezone conversion, Python/browser boundary parity, actual-record arithmetic, visible bases, idempotent responsive placement and source-day labelling. Nine focused regressions are registered in the existing dashboard and news validation commands; no workflow was triggered.

**Historical read compatibility.** Final smoke testing exposed four provider replay failures because strict complete-day validation rejected authenticated October publications using the prior same-day contract. The validator now accepts that original temporal contract only for retained publications generated before November 2, 2026, while still recomputing and checking every period against its original source records. New publications must exclude the generation day. Browser resolution already compares backend periods with the complete-day derivation and falls back when they differ. No historical fixture or preservation assertion changed. A ninth regression authenticates and validates the real retained snapshot without mutation and rejects a same-day period in a new publication. Two dashboard fallback tests use a July 27 synthetic refresh so their original July 26 observations are complete; all numerical and gate assertions remain intact.

**Intentionally unchanged and limits.** Calendar completeness does not assert exhaustive publisher coverage. Missing/zero distinctions, candidate association overlap, publisher gates, scope denominators and underlying observations remain intact. Dossier-wide race coverage and homepage active-field coverage retain their explicitly different denominator scopes, while sharing the corrected period boundaries.

## 4. Historical TF1 article in latest news

**Verified evidence.** [TF1's original article](https://www.tf1info.fr/politique/elections/presidentielle/presidentielles-2017-nicolas-dupont-aignan-devoile-son-programme-2024438.html) states publication on **February 1, 2017 at 21:06 Paris time**; its body identifies the February 1, 2017 television report. [TF1's February 1 archive](https://www.tf1info.fr/archives/2017/02-01/) corroborates the date. The current page also reports a September 24, 2026 update. Neither establishes original publication in October 2026. The normalized source publication time is `2017-02-01T20:06:00Z`.

**Reproduction and exact cause.** Retained record `c491c4023d07b5c39aee`, from Google News candidate-group discovery, supplies `published_at: 2026-10-24T06:00:57Z`. `fetch_news_wire.parse_feed` uses the RSS date without consulting the publisher's original-publication metadata. The retained item was promoted as a `positioning_integrity` development via the programme-announcement wording, and entered campaign-scoped Candidate Watch. `build_candidate_reference.build_projection` includes those campaign records in dossier latest news. PR #318's `1814a286d` historical-heading guard in `generate_recent_changes.classify_news_change` prevents What Changed promotion, but does not correct the upstream record used by these other consumers.

**Earliest safe correction.** `news_publication_corrections.py` supplies a narrowly reviewed original date for the exact Google News URL and verified TF1 article URL variants. `build_wire` applies it before deriving any public lane or analytical projection, then applies the existing rolling-window boundary. Raw inventory and corpus observations retain the received timestamp. There is no year-based headline filter and no broad ingestion-policy change.

**Affected surfaces and result.** The item disappears from both language dossiers' latest news, campaign/relevant coverage readers, candidate coverage and thematic signals. `notable_developments` changes 43→42, `relevant_news` 2529→2528, and `candidate_watch` 3598→3597. Election News remains 2075 and all its records are identical. What Changed remains byte-equivalent after newline normalization; its earlier guard remains intact. Recomputed rolling visibility/history and thematic projections no longer count the item as October 2026 activity. Settled pre-October-4 agenda history is preserved.

**Files and regressions.** New source-specific correction module and two-record frozen feed fixture; builder integration and derived artifacts listed below. The verified TF1 regression checks the corrected date without mutation and runs the full retained-inventory builder with mocked empty feeds. It preserves the raw record and excludes the historical item from every public lane. A real BFMTV October 2026 Dupont-Aignan report remains accepted. A new 2027 report referring back to a 2017 programme is also left untouched. Browser tests verify absence of the TF1 item from FR/EN dossiers.

**Uncertainty and intentional limits.** The mechanism by which Google News assigned its October timestamp is not established. The publisher's original date and this article's identity are established, so the scoped correction needs no broader policy decision. Other unresolved discovery URLs do not acquire this correction merely because they mention a year. Historical sources remain available in the raw inventory, corpus ledger, frozen regression fixture and linked publisher archive.

## Evidence preservation and generated-file review

- Authenticated unchanged files: both polling corpora, closest-runoff projection, poll study bindings, Commission notice registry and reviewed reconciliation/composite decisions, news inventory, corpus ledger, recent changes and candidate candidacy registry. SHA-256 evidence is saved in `_trace_output/audit-preservation.json`.
- Every retained public news record is field-for-field identical. The only removed ID is the verified TF1 item, in its three affected lanes. No new news observation was invented.
- Candidate agenda tracking still begins July 31, 2026. Every settled day before the recomputable October 4 boundary is identical. The supported `--previous` path was used; history was not shortened.
- The baseline manifest publication timestamp is preserved. Local derived hashes change to describe the repaired artifact family; no publication was performed.
- Candidate numerical polling evidence, classifications, scenario identities, source provenance and immutable historical fixtures are unchanged.
- Generated candidate files are included because the corrected shared periods, article associations or dependency projections flow into them. The complete list below makes their scope reviewable. The only workflow edits add the focused regression module to two existing validation commands; schedules, permissions, publication steps and source registries are unchanged.
- Main history inspected includes the earlier metric-window clarification `0713ad387`, ledger-only historical campaign fix `1814a286d`, current scope/manual-veto changes, and reviewed Commission polling fixes. No newer main commit overlapped the local repair after re-fetch.

## Validation results

Final local verification uses the workflow selections themselves, with UTF-8 inherited by subprocesses. Diagnostic logs and screenshots remain local and are excluded from the commit.

- **Complete polling production contract: 478 tests in 770.906 seconds, OK.** All 28 workflow targets ran: 475 current-data tests and three authenticated historical tests. The corrected `test_poll_semantic_labels_and_comparison_tooltip_are_updated` assertion passed within this full run. No test was skipped. Historical preservation tests and authenticated fixtures are unchanged.
- **Exact dashboard PR smoke selection: 870 tests in 425.439 seconds, OK.** This covers publication manifests, candidate/provider families and replay transactions, bilingual UI contracts, the nine audit regressions, loading behavior, news integrity and publication workflow boundaries.
- **Exact news production selection: 471 tests in 133.978 seconds, OK.** This includes relevance and scope, source health, candidate identity, visibility/agenda histories, corpus preservation, live projections, recent changes, the audit regressions, manifest validation and frontend facts.
- **Final compatibility/fallback selection: 96 tests in 105.875 seconds, OK.** The four provider replay cases also passed on untouched main (four tests in 115.020 seconds), confirming the discovered compatibility regression was repaired rather than relabelled as pre-existing. Immutable replay data and assertions were preserved.
- **Agenda/issue cross-family authority: 31 tests, 30 passed and one confirmed baseline failure.** The issue-card test expects four eligible themes while current main produces three. The same assertion fails on the untouched checkout. The earlier broader 667-case affected integration selection likewise had only this baseline failure.
- **Election scope and downstream checks:** reviewed scope CLI and all 13 scope tests passed; all 28 Radar tests passed with UTF-8. Windows CP1252 console failures disappear with UTF-8 without source changes.
- **Generated artifacts:** all five check commands passed after the compatibility correction: publication manifest, FR/EN semantic entrypoints, agenda/issue live projections and all candidate artifacts (42 FR + 42 EN dossiers, five retained archive dossiers and two hubs).
- **Responsive rendering: 14 tests passed (4.1 minutes).** Eight FR/EN cases cover 1707×932, 1100×932, 768×932 and 390×932, plus two dossier checks, two language checks and two Media Pulse interaction checks. Every homepage poll tab and scenario was exercised in FR/EN. Inspected captures show readable dates and qualifications, visible exact polling differences, score/footer separation and all six count-table rows. Escape closes the popover; no browser JavaScript errors were reported. The final compatibility correction changes neither these frontend files nor current generated artifacts.
- **Baseline failures:** all five documented methods were reproduced on untouched main and on the branch: three localization methods (footer harness and static text/ARIA assertions), the issue-card eligibility expectation and the candidate-media eligibility expectation. Together they produce four assertion failures and two locale subtest errors. No tests or registry classifications were suppressed or changed to hide them.
- **Preservation and scope:** all 12 protected files have identical Git blobs in the staged index and main and equivalent working bytes after newline normalization. Every retained public news object is identical; only the reviewed TF1 ID leaves its three affected lanes. Settled agenda history, immutable fixtures and the original publication timestamp remain intact. The explicit staging list contains 118 justified files and no diagnostics; whitespace checks pass.
- **Existing warnings preserved:** unresolved relevant Commission notices 10333, 10327, 10319, 10264 and 10260 remain warnings.

Final logs are `_trace_output/final-precommit-polling-verified.log`, `final-precommit-dashboard-verified.log`, `final-precommit-news-verified.log`, `final-precommit-compat-after.log`, `final-precommit-cross-family.log`, `final-precommit-artifacts-verified.log`, `final-precommit-baseline.log`, `final-precommit-baseline-comparison.log`, `final-precommit-provider-baseline.log` and `final-precommit-browser.log`. Final captures are under `_trace_output/final-precommit-render/`. Published-before evidence and the original preservation record remain local in the same diagnostic directory.

## Final pre-commit review

- Repeated fetches returned `24539cd1899532822d197702640e43657c5ee3c9`; there were no intervening commits, affected-file overlaps or synchronization conflicts.
- The original 117-file list was reconciled with Git's actual diff. Final smoke verification justified one additional file, `test_final_dashboard_shell.py`, containing only the synthetic refresh-date adjustment above. The final scope is 118 files: 20 source/test/workflow/documentation files, one frozen source fixture and 97 dependent generated artifacts. `index.html` contains both authored code and its generated media snapshot. Windows-only line-ending status noise adds no committed differences.
- Responsive changes keep the new date/context text readable and the article-base popover usable. The controller guard prevents redundant DOM moves; the test-server change resolves canonical directory entrypoints for English-language checks. Both workflow changes only register the audit regression module in existing commands. No schedules, permissions, publication actions or visual redesign were added.
- All 12 protected evidence files were compared again with `origin/main` after newline normalization. Every retained public news object remains identical; only the verified TF1 ID is removed. All 4,781 settled agenda daily rows before October 4, all candidate/day identities and the July 31 tracking boundary remain identical. Only Dupont-Aignan's recomputable October 24 agenda row changes.
- Publication checks passed again for the manifest, bilingual homepages, agenda/issue live projections and all candidate artifacts. The manifest retains the original publication timestamp and describes snapshot `6c49e4a08771f0eef6dbbf432bd82250891cee4b9886f23b5589e6b05ecf6d7c`.
- The reviewed election-scope CLI check and all 13 scope tests passed. All 28 Radar tests passed under UTF-8. The five documented failing methods were rerun on both the branch and the untouched main checkout with identical outcomes: four assertions and two locale subtest errors, without suppressing tests.
- Those methods are `LocalizationFoundationTests.test_footer_metric_labels_preserve_runtime_values_in_both_locales`, `.test_first_static_aria_batch_is_keyed`, `.test_first_static_text_batch_is_keyed`, `IssueSharedMetricTests.test_fr_and_en_daily_weekly_movers_and_dominance_fit_and_keep_boundary`, and `CandidateMediaPulseTests.test_ineligible_and_temporarily_missing_candidates_are_excluded` in their respective `test_localization`, `test_issue_shared_metric_authority` and `test_social_candidate_media_pulse` modules.
- Final verification logs use `_trace_output/final-precommit-*.log`; final browser captures are in `_trace_output/final-precommit-render/`. These diagnostics and temporary test directories are excluded from the explicit staging list and are not publication artifacts.

## Review assessment

**GO for the authorized focused commit and PR review**, with the confirmed main-branch failures above explicitly disclosed. This is not an all-repository-checks-green claim. Source evidence and numerical polling history are preserved. Separate authorization is required before merging; deployment and manual production workflow execution are not authorized.

## Complete changed-file list

118 files, including the generated dependent artifacts and the additional fallback fixture-date correction identified during final smoke verification.

```text
.github/workflows/update-news-wire.yml
.github/workflows/validate-dashboard.yml
agenda/live.json
assets/hybrid-dashboard.css
assets/hybrid-dashboard.js
assets/tier2-layout.js
assets/tier3-layout.css
candidate_agenda_history.json
candidate_signals.json
candidate_visibility_history.json
candidates/anasse-kazib/data.json
candidates/antoine-mikolajczak/data.json
candidates/aurore-berge/data.json
candidates/aurore-berge/index.html
candidates/benoit-mathieu/data.json
candidates/bernard-cazeneuve/data.json
candidates/bruno-le-maire/data.json
candidates/bruno-le-maire/index.html
candidates/bruno-retailleau/data.json
candidates/bruno-retailleau/index.html
candidates/david-lisnard/data.json
candidates/david-lisnard/index.html
candidates/delphine-batho/data.json
candidates/delphine-batho/index.html
candidates/dominique-de-villepin/data.json
candidates/dominique-de-villepin/index.html
candidates/edouard-philippe/data.json
candidates/edouard-philippe/index.html
candidates/emmanuel-maurel/data.json
candidates/eric-zemmour/data.json
candidates/fabien-roussel/data.json
candidates/fabien-roussel/index.html
candidates/florian-philippot/data.json
candidates/francis-lalanne/data.json
candidates/francois-asselineau/data.json
candidates/francois-baroin/data.json
candidates/francois-hollande/data.json
candidates/francois-hollande/index.html
candidates/francois-ruffin/data.json
candidates/francois-ruffin/index.html
candidates/gabriel-attal/data.json
candidates/gabriel-attal/index.html
candidates/gilles-platret/data.json
candidates/index.html
candidates/jean-lassalle/data.json
candidates/jean-luc-melenchon/data.json
candidates/jean-luc-melenchon/index.html
candidates/jean-noel-barrot/data.json
candidates/jerome-guedj/data.json
candidates/karim-bouamrane/data.json
candidates/karim-bouamrane/index.html
candidates/manolo-mlekuz/data.json
candidates/manuel-valls/data.json
candidates/marine-le-pen/data.json
candidates/marine-le-pen/index.html
candidates/marine-tondelier/data.json
candidates/marine-tondelier/index.html
candidates/matthieu-pigasse/data.json
candidates/mira-markovic/data.json
candidates/natacha-polony/data.json
candidates/natacha-polony/index.html
candidates/nathalie-arthaud/data.json
candidates/nathalie-arthaud/index.html
candidates/nicolas-dupont-aignan/data.json
candidates/nicolas-dupont-aignan/index.html
candidates/olivier-becht/data.json
candidates/olivier-faure/data.json
candidates/philippe-de-villiers/data.json
candidates/raphael-glucksmann/data.json
candidates/raphael-glucksmann/index.html
candidates/sandrine-rousseau/data.json
candidates/segolene-royal/data.json
candidates/selma-labib/data.json
candidates/sylvain-durif/data.json
candidates/teddy-riner/data.json
candidates/thierry-breton/data.json
candidates/xavier-bertrand/data.json
candidates/xavier-bertrand/index.html
docs/AUDIT_REMEDIATION_2026-11-02.md
en/candidates/aurore-berge/index.html
en/candidates/bruno-le-maire/index.html
en/candidates/bruno-retailleau/index.html
en/candidates/david-lisnard/index.html
en/candidates/delphine-batho/index.html
en/candidates/dominique-de-villepin/index.html
en/candidates/edouard-philippe/index.html
en/candidates/fabien-roussel/index.html
en/candidates/francois-hollande/index.html
en/candidates/francois-ruffin/index.html
en/candidates/gabriel-attal/index.html
en/candidates/index.html
en/candidates/jean-luc-melenchon/index.html
en/candidates/karim-bouamrane/index.html
en/candidates/marine-le-pen/index.html
en/candidates/marine-tondelier/index.html
en/candidates/natacha-polony/index.html
en/candidates/nathalie-arthaud/index.html
en/candidates/nicolas-dupont-aignan/index.html
en/candidates/raphael-glucksmann/index.html
en/candidates/xavier-bertrand/index.html
en/index.html
enjeux/live.json
fetch_news_wire.py
index.html
locales/en.js
locales/fr.js
news_publication_corrections.py
news_wire.json
publication_manifest.json
test_audit_evidence_interpretation.py
test_candidate_coverage_scope.py
test_final_dashboard_shell.py
test_fixtures/news/tf1_publication_review.json
test_frontend_facts.py
test_news_wire_relevance.py
test_runoff_workspace.py
tools/responsive-forensics/src/server.mjs
tools/responsive-forensics/tests/audit-evidence.spec.mjs
```
