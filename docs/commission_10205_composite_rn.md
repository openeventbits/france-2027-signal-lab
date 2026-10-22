# Commission notice 10205: conditional RN ballot correction

Review patch on `codex/commission-10205-composite-rn`, implementation base **`af7fbbc68e79bb20ed50cd1cb8201fe8ee31febc`**. Final fetched `origin/main` is **`e53a1e91eb7d28d52d43d5f62d6080c4073b9bbf`**; its sole newer commit refreshes the social-image asset and metadata, with no polling/runtime changes. This reviewed patch is prepared for a pull request from a separate isolated worktree. No primary or existing development checkout was edited. No production output was regenerated in the worktree.

## Decision

The existing string-based polling contract can faithfully represent the exact conditional ballot option **“Le candidat du RN, Marine Le Pen ou Jordan Bardella”**. Use it as a non-person `ballot_label`, distinct from both individuals and from generic RN. Three explicit reviewed successors replace three erroneous historical objects; all **436 unrelated active objects remain identical**. The active corpus stays **337 first-round + 102 runoff = 439**. There is no new survey, duplicated configuration, candidate profile or candidacy declaration.

The separate review `FR27-10205-COMPOSITE-RN` includes three correction decisions `FR27-10205-C1/C2/C3` and exact notice-identity decision `FR27-10205-NOTICE-IDENTITY`. The Batch 2 unresolved review remains immutable as historical evidence. Its outcome is superseded for this notice only after the new exact identity and complete three-successor collection checks pass.

## Original-document evidence

Primary source: [Commission notice 10205, original OpinionWay/JDD PDF](https://www.commission-des-sondages.fr/notices/files/notices/2026/juin/10205-pres-iv-opinionway-jdd-13-juin.pdf). Original file SHA-256 **`c22521b061c86f448e5779fdfb89bf1728c6100efc837775d39b70ec72c0a90d`**. A fresh download matches the recorded Batch 2 original evidence exactly. Methodology and all result pages were rendered and independently visually checked; the PDF and page renders are retained outside the checkout in `composite-10205-validation/evidence/`.

- PDF p2: OpinionWay; commissioner and buyer Le Journal du Dimanche.
- PDF p3: online quota survey, **10–11 June 2026**; **901 registered voters drawn from 1,001 adults aged 18+**. The published intention column uses respondents certain to vote (notes 9+10), with the stated sociodemographic/2022 presidential weighting.
- PDF p4 and table headers pp12–14 distinguish the **683 certain-to-vote** base from the 901 registered-voter base. The document does not supply a separate expressed-respondent count for each configuration; none is invented.
- PDF pp12–14: three current first-round tables. Transcription uses the explicit **Publié** column, not raw values or an alternative weighting column. Published non-expression percentages are 16%, 15% and 16%, separately from the candidate shares, which each total 100%.
- The RN row is one conditional ballot option with scores **35%, 33%, 34%**. It is neither a split score nor an individual score for either person. No runoff result is admitted or changed.

**Sample preservation decision:** all three predecessor `sample_size=1001` values and their legacy scope representations remain exact (`reported` for the two migrated objects; absent on the legacy third object). The correction does not relabel 1,001 as registered voters, substitute 901 or 683, or infer an expressed denominator. The distinct source bases and methodology pages are explicit in the immutable review evidence. Existing public wave sample fields still show the legacy reported value; this patch does not undertake an additional sample-metadata correction.

## Full original published tables

### Configuration 1 — PDF page 12

| Published ballot option | Published score |
|---|---|
| Nathalie Arthaud | 1% |
| Jean-Luc Mélenchon | 13% |
| Fabien Roussel | 4% |
| Marine Tondelier | 4% |
| Raphaël Glucksmann | 14% |
| Gabriel Attal | 14% |
| Bruno Retailleau | 9% |
| Nicolas Dupont-Aignan | 2% |
| Éric Zemmour | 4% |
| Le candidat du RN, Marine Le Pen ou Jordan Bardella | 35% |

### Configuration 2 — PDF page 13

| Published ballot option | Published score |
|---|---|
| Nathalie Arthaud | 1% |
| Jean-Luc Mélenchon | 13% |
| Fabien Roussel | 3% |
| Marine Tondelier | 5% |
| Raphaël Glucksmann | 13% |
| Édouard Philippe | 19% |
| Bruno Retailleau | 8% |
| Nicolas Dupont-Aignan | 2% |
| Éric Zemmour | 3% |
| Le candidat du RN, Marine Le Pen ou Jordan Bardella | 33% |

### Configuration 3 — PDF page 14

| Published ballot option | Published score |
|---|---|
| Nathalie Arthaud | 1% |
| Jean-Luc Mélenchon | 16% |
| Raphaël Glucksmann | 16% |
| Édouard Philippe | 19% |
| Bruno Retailleau | 9% |
| Nicolas Dupont-Aignan | 2% |
| Éric Zemmour | 3% |
| Le candidat du RN, Marine Le Pen ou Jordan Bardella | 34% |

All other source scores match the predecessor objects after the already-reviewed individual aliases are compared. Candidate order, other candidate labels, numeric types, fieldwork, commissioners, publication-date fields, source URLs and sample fields are preserved exactly. The third event retains its JDD reporting URL and abbreviated individual labels; each successor separately records the original PDF URL/hash/page as reviewed provenance.

## Root cause and downstream audit

Two historical migration outcomes stored the discovery feed's individual label `Jordan Bardella`; the legacy third event stored `Bardella`. The original conditional RN row was not retained. Polling Lab's finite alias directory therefore classified all three as one person. Historical retention then protected those incorrect objects against later discovery changes. This is a factual identity error in retained data, not a classifier failure.

| Consumer | Before | Corrected behavior |
|---|---|---|
| `polls.json` / retention | Three active individual-Bardella representations | Explicit new successors; immutable predecessors retained in the review snapshot; no direct production JSON edit |
| `poll_contract.py` | Deterministic scenario/event hashes over labels/hypotheses | Contract unchanged; exact composite label creates new scenario keys and hypotheses, hence new valid event IDs |
| `poll_migration.py` | Reviewed finite individual identities | Accept only the exact reviewed composite string as its own distinct identity; no fuzzy alias, generic RN mapping or alias to either person |
| `fetch_polls.py` | Older migrations require their exact historical canonical objects | Validate the exact later successors first; present checked immutable predecessor snapshots only internally to older contracts; publish the three verified successors after those contracts pass |
| Polling Lab / `build_poll_explorer.py` | Three scenario observations and one wave counted as Bardella | Composite `identity_type=ballot_label`; preserved in source-result lists, excluded from the person directory, chart series, picker, ranges and rankings |
| Candidate Signals / histories | Two canonical-name entries yield a 33–35% Bardella range for this package; the legacy abbreviated third does not resolve to the canonical roster | Neither Bardella nor Le Pen receives any of these conditional scores; explicit ballot-type guards also reject attribution if an arbitrary matching roster is supplied |
| Candidate dossiers | Bardella history includes this June package | Its erroneous package observation is removed; no composite dossier, candidate record or candidacy status is generated |
| Race at a Glance | Latest featured October package; earlier candidate comparisons can encounter June scores | Latest featured package unchanged; exact name identity prevents the conditional score becoming an individual earlier observation |
| Legacy home-page freshness / pair picker | Raw labels are enumerated as candidate entries | Source-template JavaScript excludes the explicitly flagged `ballot_label` entries from individual freshness rows and the ordinary comparison picker; complete lineup results retain the translated conditional label |
| Static poll pages / links | Existing wave page groups all three configurations | Same French/English wave routes; exact conditional option shown in both languages; non-person option excluded from individual variation summaries |
| Publication manifests | Four unresolved Commission warnings | Complete checked 10205 coverage leaves only 10327, 10264 and 10260 unresolved |

The English display is **“The RN candidate, Marine Le Pen or Jordan Bardella”**. The exact original French label remains in the event and explorer provenance. Both published identities remain distinct from `jordan-bardella` and `marine-le-pen`. Existing ordinary individual events are object-identical.

## Exact supersession lineage

| PDF page | Historical predecessor ID | Corrected successor ID | RN conditional score |
|---|---|---|---|
| 12 | `18c3f04dfcd854092bfaddba00a48f75bb6c129f483507dc9f880a1065657210` | `848136fabb27a00e5c4750c43d85a473d5c44eda4053172ce49e665cfec4b5b1` | 35% |
| 13 | `97585f1475829d9d8af92d50051dc40d3fc7e515c8c5bed45e8ce8c5c9f50085` | `cc8b033310b2a4b15c846e903591628d8aee9f5df97d0411c86e1b5385e02f83` | 33% |
| 14 | `992208751ce22334e7b107c86d1b2cf2bf0ab411fcb4bd97df1bf6bde8734900` | `0697cffa94c94e93729c21f560ec37aea5513c53fe6c43a3f75763101422b381` | 34.0% |

The exact three predecessor objects are embedded in `fr27_commission_10205_composite_review.json`, not reconstructed from a loose score key. The first two predecessor snapshots preserve their earlier `supersedes_event_id` values:

- `3720d46369d9dc9629d3ce8d80bad3740c0b43845c3a8f7e77f2cc4620a7dd08` → `18c3f04dfcd854092bfaddba00a48f75bb6c129f483507dc9f880a1065657210` → `848136fabb27a00e5c4750c43d85a473d5c44eda4053172ce49e665cfec4b5b1`.
- `ed26935dd3b45aadc1c1e142351b7c357d10f45e2a36219ba6309962b47a4092` → `97585f1475829d9d8af92d50051dc40d3fc7e515c8c5bed45e8ce8c5c9f50085` → `cc8b033310b2a4b15c846e903591628d8aee9f5df97d0411c86e1b5385e02f83`.
- `992208751ce22334e7b107c86d1b2cf2bf0ab411fcb4bd97df1bf6bde8734900` → `0697cffa94c94e93729c21f560ec37aea5513c53fe6c43a3f75763101422b381`.

The three `supersedes_event_id` fields point to immediate predecessors; earlier links remain in immutable snapshots. All predecessors are absent from the corrected active archive. IDs use the existing deterministic contract, with preserved source URLs and dates. No historical ID is modified in place.

Review canonical SHA-256 **`63984973841b138a1c13ab88460e988e49cdf2acb32f0bdb7d28c477c34ed168`**. Changing any evidence, predecessor, successor, source variant or notice identity requires a new explicit review. Exact canonical JSON comparison also rejects integer/float/boolean representation changes that Python equality would conflate. Exact current-source variants are accepted by facts and provenance, never locator alone. Missing, altered, duplicate, simultaneous or incompatible historical objects fail closed; source score/sample/provenance/lineup drift cannot select a new outcome.

## Compatibility and retention protections

The internal compatibility view addresses an actual existing constraint: two old objects are canonical outputs of an earlier migration. A naive new label caused that older boundary to reject missing canonical events. `prepare_composite_history()` first validates the complete exact before/after states and incoming evidence, then supplies only the embedded predecessor snapshots to the unchanged older migration contracts. `finalize_composite_history()` reapplies the authorized successors after those contracts and their retention/extraction guards succeed. The view is never published. This also works when an older Wikipedia revision is replayed after the new correction: the validated review remains active, and all three old identities stay inactive.

`poll_contract.py`, `rehearse_fr_poll_migration.py`, the original cutover hashes and separately approved barometer hash decisions remain unchanged. All existing Batch 1, Batch 2, earlier first-round and runoff registries remain unchanged. All **41 existing historical fixture files** are unchanged. The new exact composite identity does not alter any frozen source extraction.

The existing Batch 2 integration regression now permits exactly these three reviewed successors and still compares every other object exactly, preserves both Batch 2 admissions and checks all nine Batch 1 outcomes. A separate classifier regression was already failing on untouched main after production deployment because it assumed the live registry still contained pre-deployment excluded states. It now constructs that historical excluded input explicitly; the production classifier and coverage logic are unchanged. Baseline failure proof is retained as `baseline-discovery-failure.log`.

## Notice coverage decision

The new identity decision accepts exactly two snapshots of notice 10205: the older Batch 2 identity with absent structured survey metadata, and the same exact identity with extracted **2026-06-10–2026-06-11** dates. Both pin the same original PDF SHA-256, listing URL/title/date, institute/commissioner, resolved official URL and first-round evidence. No other structured date or source variation is accepted. Successful original-document eligibility is still required; arbitrary unsupported or failed-fetch evidence cannot reconcile.

After Batch 2 coverage runs, the separate 10205 reconciliation requires all three complete corrected objects, including exact label semantics, scores, samples, IDs, lineage and provenance. Missing/extra/duplicate/changed configurations keep the notice unresolved. On the validated live temporary output, 10205 is **reconciled** under `reviewed_10205_complete_composite_configurations`, with all three successor IDs above.

Coverage changes **39 relevant / 3 parsed / 32 reconciled / 4 unresolved** → **39 relevant / 3 parsed / 33 reconciled / 3 unresolved**. A complete live registry comparison proves that no other Commission review outcome changes (`notice-coverage-comparison.json`). The remaining warnings are:

- **10327:** Arthaud's literal dash versus numeric zero remains unresolved.
- **10264:** Sébastien Bonnal `<1%` cannot be faithfully represented by the existing numeric contract.
- **10260:** the third first-round configuration has Arthaud and Bouamrane `<1%`; existing admitted numeric configurations and runoff observations are unchanged.

## Before/after projections and methodological consequences

- Polling Lab Bardella scenario count: **102 → 99**; wave count **32 → 31**; his overall **23–38.5%** range is unchanged. Le Pen retains **232** scenarios, **68** waves and his **25.5–40%** range. The composite option is absent from the person directory and both individual series.
- Candidate Signals June-wave Bardella range: **33–35% in two canonical-name hypotheses → not observed**. The third abbreviated legacy event had not resolved to that roster. No conditional score is transferred to Le Pen.
- Bardella historical package count: **15 → 14**. Le Pen's history remains unchanged.
- All other individual source scores, published ranges and the latest featured Race at a Glance package are unchanged.
- Existing deterministic sorting by scenario key changes the June package's representative scenario from configuration 3 to configuration 2 after its label changes. The code does not introduce a new selection method or pin an arbitrary display order. Consequently some June selected historical points become present where the former abbreviated selected lineup did not resolve, and Glucksmann's selected point is **16 → 13** from the newly selected, fully published configuration. Its source range remains **13–16**. June package source-link order also changes. Ten other candidate-history objects reflect only this representative/source-order effect; their scores are not corrected or invented. See `candidate-history-comparison-live.json` and `wave-projection-comparison-live.json` for every before/after field.

The review deliberately preserves legacy sample fields and existing representative-selection methodology. It does not interpret the composite as two candidates, declare either person a formal candidate, redistribute its support, normalize unrelated abbreviated labels or change other polling scores. Future changed source representations require review and fail closed rather than restoring individual attribution.

## Validation

- Focused discovery/coverage, new correction, Batch 1, Batch 2, Phase 1 and cutover suite: **169 passed in 243.704s** (`focused-reviewed-final.log`). Includes **28 new correction tests**; exact source tables, unrelated-object preservation, lineage/collisions, repeated ingestion, three older source snapshots, individual projections, bilingual results and exact complete coverage are covered.
- Broad polling/publication and relevant frontend/candidate suite: **1195 passed in 1065.985s**, 32 modules (`broad-reviewed-final.log`), using the fully regenerated disposable publication copy.
- First production-equivalent live French fetch: **exit 0**, latest source revision **240570516**; temporary outputs only in `fetch-live/`. **337 first-round + 102 runoff**, all **436 unrelated objects identical** by canonical per-event JSON. All five reviewed runoff successors remain exact.
- Repeated production-equivalent fetch using corrected temporary outputs as prior inputs: **exit 0** (`repeat-live-fetch.log`); all 337 first-round objects, 102 runoff objects and the entire Commission registry are identical. A further final fetch after stricter JSON snapshot validation also exited 0 (`final-live-fetch.log`).
- Extraction diagnostics remain **293/293 first-round and 100/100 runoff**, zero shortfall, unchanged **90%** guard floor. Batch 2 reports `0 admitted; 2 already applied`.
- All **23 disposable publication generation/check commands passed**, including all-active individual candidate dossiers, candidates hubs, Candidate Signals, recent changes, explorer, section launcher, polling pages/hub, bilingual routes/search, sitemaps and manifest. **80 waves, 337 scenarios, 160 bilingual poll pages, 324 routes**; snapshot `11d8b0a9cbf8e81cad1f5d177b863cd9d3c281cacc2ca55e24bb4e5cef6664c3`.
- Home-page executable scripts and Polling Lab asset passed JavaScript syntax compilation (**5 script blocks**). New non-person flags preserve complete result displays while removing the composite from individual comparisons.
- Early tests caught the older-revision reactivation bug in the first compatibility implementation; it was fixed and the final 169-test focused run passes. An intermediate run also hit sandbox-default temporary-directory cleanup permissions; final runners use the writable external validation directory. No guard was bypassed.

The final page-by-page comparison proves **146 of 160 historical polling pages are byte-identical** to regeneration with the pristine baseline. Two June OpinionWay pages reflect the corrected ballot. The only change in twelve nearby pages is their related-card count for that June wave: **11 → 10 individual candidates**, because the RN option is not a person. Every other byte on those twelve pages is identical (`related-page-preservation.json`). Existing April 2025 Harris generic-label variation summaries are preserved by a dedicated regression.

The initial broad check against deliberately unmodified tracked publication artifacts correctly reported stale hashes for the two home pages and two Polling Lab routes. Regeneration/checks therefore run in the disposable publication copy, never by editing tracked outputs. That post-deployment run also exposed three narrow test assumptions: an intermediate migration ID was assumed permanently active, the current coverage regression omitted the new exact reviewed layer, and an English-page assertion used the default French label. The final tests explicitly validate the authorized compatibility view, reproduce the deployed reconciliation layers, and assert the English translation; their existing exact-object assertions remain.

Extra localization probes outside the standard polling suite reproduce **two assertion failures and two footer-harness subtest errors on untouched main** (three test methods; `baseline-localization-probes.log`). They concern pre-existing static localization/footer expectations, not this ballot label. They are documented and left outside this source-accuracy patch.

All generated outputs, original PDFs, page images, logs and machine-readable comparisons are outside the worktree in `composite-10205-validation/`. The committed-production JSON inputs remain untouched; these corrected objects are produced only through the reviewed ingestion boundary.

## Exact changed files

| File | Functions / purpose |
|---|---|
| `fr27_commission_10205_composite_review.json` | Immutable original evidence, three predecessor/successor decisions and separate exact notice identity decision |
| `reviewed_composite_rn.py` | `load_composite_review()`, `reconcile_composite_rn()`, `prepare_composite_history()`, `finalize_composite_history()`, `reconcile_composite_notice_coverage()`; exact correction and compatibility/coverage checks |
| `poll_ballot_labels.py` | One exact conditional ballot label and FR/EN display names; no candidate aliases |
| `poll_migration.py` | `reviewed_candidate_name()` accepts only this exact distinct reviewed ballot string |
| `fetch_polls.py` | `integrate_french_migration_source()` compatibility and final supersession boundary; `main()` invokes exact 10205 coverage after Batch 2 |
| `build_poll_explorer.py` | Existing `BALLOT_LABEL_IDENTITIES` extended by one option; `_scenario_projection()` supplies its bilingual display names |
| `build_candidate_signals.py` | `project_candidate_polling()` excludes explicit non-person options from individual ranges, histories and selected ranks |
| `build_poll_pages.py` | `candidate_label()` / `render_scenario()` localize the option; `candidate_variation_rows()` excludes only the reviewed conditional RN option; unrelated generic-label summaries remain unchanged |
| `assets/polling-lab.js` | Bilingual complete-result/lineup labels; existing person-only chart and comparison filters remain |
| `index.html`, `en/index.html` | Four narrow home-page source JavaScript edits: preserve ballot metadata, exclude it from freshness and pair pickers, translate full lineup results; no generated content block was edited |
| `.github/workflows/update-polls.yml` | Add the new test module to the existing test step; no trigger or production command change |
| `test_commission_10205_composite.py` | 28 original-document, supersession, projection, preservation, replay, bilingual, scope-preservation and coverage regressions |
| `test_fixtures/fr27_polling/commission_10205_document.json.gz` | New frozen exact methodology/result-page extract with original PDF identity; no earlier fixture edited |
| `test_commission_coverage_batch2.py` | Integration expectation recognizes only these three approved successor objects; all other preservation assertions stay exact |
| `test_commission_notice_discovery.py` | Explicit historical excluded-state setup independent of deployed live registry coverage |
| `test_post_audit_first_round_corrections.py` | Validate the exact later successor state, then exercise the unchanged older expansion contract through its authorized compatibility view |
| `test_commission_notice_coverage.py` | Reproduce the new exact 10205 reconciliation layer when validating an already deployed corrected registry |
| `test_poll_pages.py` | Assert the English result label on English pages |
| `docs/commission_10205_composite_rn.md` | This English review report |

## Final diff and worktree status

`git diff --check` passes. The implementation base is `af7fbbc68e79bb20ed50cd1cb8201fe8ee31febc`; the reviewed upstream base is `e53a1e91eb7d28d52d43d5f62d6080c4073b9bbf`. The sole intervening commit, **“Refresh OG cover”**, changes the PNG and social-image cache-busting metadata in 164 pages. The two home-page filenames overlap this patch, but their metadata hunks are separate from the polling JavaScript changes. No Python/JavaScript logic, polling dataset, workflow, test or historical fixture changed upstream. The complete reviewed patch passed `git apply --check` against both bases. PR preparation commits the approved changes and rebases this isolated branch onto current main, with exact implementation, evidence and historical-snapshot preservation checks. Final commit identity and post-rebase validation results are recorded in the PR description.

The patch contains exactly **20 files**: 14 existing files and six additions, including this report. The complete binary-capable reviewed diff, original file digests and validation evidence remain outside the checkout in `composite-10205-validation/`. Production JSON, generated publication artifacts and all pre-existing historical fixtures are excluded from the patch. This report retains the original review-stage validation results; the PR description records the finalization reruns. No merge, deployment or manual production workflow execution is authorized.
