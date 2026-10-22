# Commission election-barometer classifier review

Branch `codex/commission-barometer-classifier`. Original implementation base: `cfd9cee36cbdbac47cc46f716d014a18ef266a14` (merged Batch 2 plus production update). This reviewed patch is prepared for a pull request. No polling observation is admitted, corrected or superseded. Published baseline remains **337 first-round + 102 runoff = 439 event objects**.

## Root cause and bounded correction

`classify_listing()` recognized explicit voting markers before applying negative words. The two bare titles “Barometre election V6/V7 IFOP” lacked those positive markers, so the generic `barometre` negative prevented document inspection. The new presidential-category rule recognizes adjacent “barometre [de] [l] election” only when no other negative subject applies. It returns **ambiguous / inspect**, never eligible from the title. Popularity, image, stature, personality, confidence and non-presidential surveys retain their exclusions; the generic barometer exclusion remains. The existing `IV` path for 10242 is unchanged.

Independent PDF inspection found a second issue: the original `confirm_document_eligibility()` rejected both documents despite explicit 2027 context on PDF p8, because their phrase is “élection présidentielle qui aura lieu le 18 avril 2027.” A narrow dated-election phrase now supplies that context only when the document also identifies itself as a presidential-election barometer. The independent voting-intention-language requirement remains mandatory; an election date or likelihood-to-vote question alone cannot establish eligibility. Fetch errors and malformed PDF evidence retain fail-closed behavior.

## Eligibility and coverage decisions

All methodology and current result tables were visually inspected. PDF references are one-based file pages. The original Commission PDFs are retained outside the checkout in `barometer-validation/evidence/`; their SHA-256 values were measured directly. The 10327 hash also agrees with Batch 2’s previously reviewed original-source hash.

Both original reports identify Ifop-Fiducial as the institute and LCI, Le Figaro and Sud Radio as commissioners (methodology p2). The discovery registry retains its original listing metadata: institute `Ifop`, commissioner null for 10327 and `Le Figaro` for 10284. The audit distinguishes that listing representation from the complete original-document attribution; no historical polling commissioner or provenance field is rewritten.

| Notice / primary document | SHA-256 | Methodology and voting evidence | Before → after classification | Coverage decision |
|---|---|---|---|---|
| [10327](https://www.commission-des-sondages.fr/notices/files/notices/2026/octobre/10327-pres-barometre-election-v7-ifop-20-octobre.pdf) | `39b82377458a44db5c7de3ad95ca4f7938f87dd791163083206538c32795fac5` | p2: 2026-10-17–2026-10-19; 1928 registered voters from 2081 adults. p8: explicit dated 2027 election. first round pp9–16 (eight); runoff pp17–21 (five). | `excluded_non_voting` → document-confirmed `eligible` during discovery → `unsupported` at production collection because no parser is registered | **unresolved**. All eight first-round and five runoff lineups are present, but page 14 publishes Nathalie Arthaud as a literal dash while event a6d09b740934d4b95164c89ddd27edaede1ed2dff16d0b139b5924657217b03c records numeric zero. Full faithful numerical coverage is not established. Preserve all events and leave this representation issue unresolved. |
| [10284](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10284-pres-barometre-election-v6-ifop-30-septembre.pdf) | `6a12dfe921c0582829f54cf5d71ed694099453d18bed13fbd011e83122b59e09` | p2: 2026-09-25–2026-09-29; 1393 registered voters from 1527 adults. p8: explicit dated 2027 election. first round pp9–18 (ten); no runoff result table in this PDF. | `excluded_non_voting` → document-confirmed `eligible` during discovery → `unsupported` at production collection because no parser is registered | **reconciled**. All ten complete original first-round tables match the ten existing reviewed registered-voter objects exactly. The original PDF contains no runoff result table; no new observation is admitted. |

The existing production contract distinguishes confirmed eligibility from parser support: `fetch_official_events()` relabels confirmed eligible notices without a registered parser as `unsupported`. This patch preserves that behavior and does not introduce parsers. Exact coverage may recognize that specific confirmation/no-parser reason plus the original hash and complete evidence; an arbitrary unsupported notice cannot acquire supported coverage.

**Two official 10284 PDF versions:** the current listing redirects to the primary filename/hash above. The older official URL `https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10284-pres-barometre-election-presidentielle-v6-ifop-le-figaro-30-septembre.pdf` has SHA-256 `ed665185fb1bae1a07d477439844c359eb9e4c158ccc7f7e6fa8a7783ed82dd9`. All methodology and relevant result pages render identically except pages 12–13, which have layout-only differences and were independently inspected. All ten candidate-score lists and sample bases match exactly across both documents. Coverage pins the current listing PDF only; the archived hash is supplementary evidence, not a wildcard or automatic alias.

Both notices are eligible voting-intention documents. Eligibility does not imply complete numerical coverage. Every original lineup is already represented: no missing configuration or duplicate admission is established. All ten 10284 tables agree exactly with existing reviewed registered-voter objects. Notice 10327 has twelve exact numeric table matches and one unresolved literal-score correspondence; it is not cleared merely because the survey is present.

**Separate historical representation issue, preserved:** notice 10327 p14 prints Nathalie Arthaud as `-`, while existing event `a6d09b740934d4b95164c89ddd27edaede1ed2dff16d0b139b5924657217b03c` stores numeric `0`. The other thirteen candidate scores agree and total 100. This patch does not interpret the dash, remove Arthaud, change the score or alter that event’s identity. A separate reviewed source-semantics decision is required to establish faithful equivalence; 10327 remains unresolved.

**Sample semantics:** 10327 has 1,928 registered voters from 2,081 adults; fieldwork starts 17 October at 20:00 and ends 19 October. The existing date extractor cannot parse the start-hour interruption, so automatic `survey_metadata` remains absent; the audit records the original dates without changing the date parser. 10284 has 1,393 registered voters from 1,527 adults, 25–29 September. Expressed-intention and certain-voter-expressed counts below are separate matchup/configuration bases, not replacements for the registered-voter parent sample. Existing seven 10327 first-round `reported` scopes, the registered-voter Ruffin–Polony scope and five runoff successor scopes remain unchanged.

## Complete table comparison

All candidate names and literal published scores are transcribed in `fr27_commission_barometer_review.json`; a literal dash is retained as a string. The table lists every current configuration, exact existing event ID and distinct source bases.

| Notice / PDF page | Round | Existing event ID | Registered / expressed / certain-expressed | Comparison |
|---|---|---|---|---|
| 10327 / 9 | first_round | `0351425b11831a87a3d54045c23ff74de50f8558e935b148558104eb9fa40a4b` | 1928 / 1431 / 1159 | complete numeric table exact |
| 10327 / 10 | first_round | `29fb575d9bdfa7623e1d35a64c237db04c12fb0c995b7d5508ae20be0f2c5254` | 1928 / 1421 / 1145 | complete numeric table exact |
| 10327 / 11 | first_round | `944f7fabf47b3a9e40dc7c862c16c0c72db61878ae0a6e00b9cb5fbf84c84fb9` | 1928 / 1402 / 1129 | complete numeric table exact |
| 10327 / 12 | first_round | `7679a530045044d6cad8cbb16edc2234d5611b709ef8d874f67356501840beed` | 1928 / 1408 / 1138 | complete numeric table exact |
| 10327 / 13 | first_round | `9f33fd416a66b1ed0a57260cd84fbe566de7763c32ac5aca10287dff04cbc30f` | 1928 / 1360 / 1101 | complete numeric table exact |
| 10327 / 14 | first_round | `a6d09b740934d4b95164c89ddd27edaede1ed2dff16d0b139b5924657217b03c` | 1928 / 1463 / 1179 | Arthaud `-` vs existing `0`; all other scores exact |
| 10327 / 15 | first_round | `8fe53598df7beccd2a35b46ae6f8560e16c6f801843378505609a6d2a0d68bc7` | 1928 / 1439 / 1158 | complete numeric table exact |
| 10327 / 16 | first_round | `458cb1a84a083ed5be2c5275b0e20fe0988fab911b9090ae7a5cc0611b4f642e` | 1928 / 1451 / 1164 | complete numeric table exact |
| 10327 / 17 | second_round | `115ff210edfe581876a9fae703475ecec7f608b2312df5d2ce64941e7ec4117a` | 1928 / 1240 / 981 | complete numeric table exact |
| 10327 / 18 | second_round | `3e337be6f1827ed917ec83139951a27de24713fbc93cb0249150b7f9ebf08677` | 1928 / 1383 / 1095 | complete numeric table exact |
| 10327 / 19 | second_round | `dc48e1acd3d243666e98420673a25411d08adb73f2ef7375632e52f548be17a2` | 1928 / 1346 / 1063 | complete numeric table exact |
| 10327 / 20 | second_round | `e97f8a9a7ba535b47a0b2c191562fa86bbcf8e38ee904d213a5b180541c62d88` | 1928 / 1314 / 1044 | complete numeric table exact |
| 10327 / 21 | second_round | `ca79c8681e49e780251417d6d916c3d5df2cbabefa17d3a831a978ee148aa553` | 1928 / 1345 / 1061 | complete numeric table exact |
| 10284 / 9 | first_round | `3faf55681bc28ffd2da5210c65a232b263e8825879539f9fa3a93e22669bfc44` | 1393 / 1027 / 837 | complete numeric table exact |
| 10284 / 10 | first_round | `5810eda3138de004f8f5775c96b3f7b3620abbe6086e00af87829267c1398409` | 1393 / 1003 / 817 | complete numeric table exact |
| 10284 / 11 | first_round | `cca95266da8cc497acc3ea505c8a5397880c626b0e7d264fed3f4ffc7c69a190` | 1393 / 970 / 792 | complete numeric table exact |
| 10284 / 12 | first_round | `dc7deea05ea268e319016dcbae38cd6a362d4b8f3428b11a9982d89cc02491e5` | 1393 / 928 / 763 | complete numeric table exact |
| 10284 / 13 | first_round | `e938c80b676988665c0bedc3f87f835f5f12c875306931e833290167068233e7` | 1393 / 964 / 785 | complete numeric table exact |
| 10284 / 14 | first_round | `12a0639abdc7d065ae67b0a4613c2b56a3cf8f854bad12c628e46bf982e1b5eb` | 1393 / 974 / 796 | complete numeric table exact |
| 10284 / 15 | first_round | `d6a2cb3620d25f29157b0654965fcfb52d1a21ab3f18b519661468502bd05f54` | 1393 / 971 / 795 | complete numeric table exact |
| 10284 / 16 | first_round | `40f28f59058261a5f0f984caf39f816c612a06b0e11d36b6daabdb1737c4914e` | 1393 / 969 / 799 | complete numeric table exact |
| 10284 / 17 | first_round | `6f6756d00e9d2a390e9e55c7883ee66bc383d47f257f49fa00e49d1e48367ec9` | 1393 / 980 / 809 | complete numeric table exact |
| 10284 / 18 | first_round | `7ae37b33f52f31df34aa2b1fd0e5a326fff1c7e6b8683255b30472d9fb44309a` | 1393 / 1015 / 827 | complete numeric table exact |

## Exact coverage safeguards

The coverage exception is limited to these two notice IDs and a canonical-hash-pinned review bundle. It requires positive document eligibility, exact listing/source identity, original PDF hash, expected rounds and structured metadata. Notice 10284 additionally requires the canonical SHA-256 of all ten complete published objects, sorted by event ID. This includes every score, sample, candidate, ID, lineage and provenance field. Missing, extra, duplicate or changed objects remain unresolved; a single matching observation cannot clear the notice. Notice 10327 is explicitly unresolved even when all thirteen existing configurations are present. Generic coverage behavior for other notices is unchanged.

The Batch 1 and Batch 2 registries, their source variants and all canonical corrections/admissions/supersessions are untouched. No candidate normalization, candidacy status, polling contract, extraction-loss behavior or historical fixture is modified.

The full suite initially exposed a whole-file cutover hash check that correctly rejected the requested edits. `rehearse_fr_poll_migration.py` retains the original three `PHASE4_PROTECTED_LOGIC_SHA256` values exactly. A separate `POST_CUTOVER_LOGIC_REVIEWS` decision pins only the exact new discovery and coverage file hashes, anchored to their historical hashes and this review ID. No file is removed from protection; the polling-contract pin, historical event-ID probes, original cutover counts and extraction-loss floors remain unchanged. Tests append an unreviewed change to each of the three protected files and confirm that every case still fails.

## Validation

- Final broad polling/publication suite: **1167 tests passed in 1089.732 seconds**, across the same 31 modules used for Batch 2. Log: `polling-publication-final.log`.
- Final focused discovery, coverage, Batch 1, Batch 2, Phase 1 and cutover verification: **141 tests passed in 207.585 seconds**. This includes 23 new classifier/coverage/hash-guard regressions, all 21 Phase 1 stability tests, all 21 Batch 1 tests and all 27 Batch 2 tests. Log: `focused-final.log`.
- The first broad run correctly failed one historical whole-file hash check. The original three hashes remain immutable, the exact later review is separately recorded, and the final cutover test passes. The new mutation regressions still reject unreviewed changes to discovery, coverage and the polling contract.
- Final production-equivalent live French fetch exited **0**, Wikipedia revision **240570516**, with all four outputs in `barometer-validation/fetch-final/`. Existing source guards report **293/293** first-round and **100/100** runoff extraction, no loss, and the same 90% failure floor. Batch 2 reports `0 admitted; 2 already applied`. Log: `production-equivalent-fetch-final.log`.
- The before/after comparison proves **all 439 published event objects are identical**, including canonical per-event JSON representation; no event or configuration is added or removed. First round remains **337**, runoff **102**. All nine Batch 1 outcomes, five runoff supersessions and both Batch 2 admissions are exact. Evidence: `output-validation.json`.
- Only the two targeted titles change their listing-level decision when replayed across the complete original registry. Genuine negative barometers remain excluded. Repeated discovery preserves timestamps and is identical; repeated exact coverage is idempotent. Missing/changed hashes, rounds, sources, samples, lineages, scores and configurations cannot authorize reconciliation.
- All **19 downstream publication generation/check commands passed**, using a disposable copy with the final code and fetched outputs: candidate signals, recent changes, explorer, section launcher, polling pages/hub, bilingual routes, search, sitemaps and publication manifest. Outputs: **80 waves, 337 scenarios, 160 bilingual poll pages, 324 routes**; manifest validated snapshot `dea90b72bbf47ca10466c23c646577a0b2cd804e98c2c1434a6a2a08a87d8869`. Four unresolved-notice warnings remain visible. Log: `publication-validation.log`.

Coverage summary changes from **37 relevant / 3 parsed / 31 reconciled / 3 unresolved** to **39 relevant / 3 parsed / 32 reconciled / 4 unresolved**. Both barometers are now inspected and voting eligibility is confirmed; production stores them as `unsupported` solely because no parser is registered. Notice 10284 reconciles only on complete exact evidence; notice 10327 stays unresolved.

Two unrelated live-discovery observations are documented rather than silently repaired: the new listing 10328 is excluded for lacking voting-intention language; and the existing extractor supplies structured fieldwork dates for 10205 that its Batch 2 identity snapshot did not record. Baseline and patched code return exactly the same eligibility/dates on the identical original 10205 PDF (`10205-confirmation-comparison.txt`). Its exact review therefore remains fail-closed (`reviewed_notice_identity_mismatch`), in addition to the known composite-candidate issue. Notice 10242 retains the identical complete Batch 2 coverage collection; its parser-status reason now reflects successful document confirmation.

The first temporary fetch and its conservative intermediate results are retained as `production-equivalent-fetch.log`. No failed guard was bypassed. All PDFs, image comparisons, logs and temporary outputs are retained outside the checkout in the existing `barometer-validation` directory.

## Remaining unresolved notices

- **10327:** the page-14 literal dash versus numeric zero correspondence described above.
- **10264:** Sébastien Bonnal is published `<1%`; the numeric score contract cannot represent that bound faithfully.
- **10260:** the third first-round hypothesis publishes Arthaud and Bouamrane `<1%`; its two admitted numeric first-round configurations and two runoffs remain unchanged.
- **10205:** outstanding historical candidate-representation issue: the source tests one composite “Marine Le Pen ou Jordan Bardella” RN option, while three historical events assign its scores to Jordan Bardella alone. Those events and the unresolved warning remain unchanged.

## Changed files and final diff

- `commission_notice_discovery.py`: `classify_listing()` and `confirm_document_eligibility()` only; narrow listing and original-document wording handling.
- `commission_notice_coverage.py`: `_canonical_sha256()`, `_reviewed_barometer_coverage()` and the two-notice hook in `reconcile_commission_notices()`; no change to generic matching for other notices.
- `rehearse_fr_poll_migration.py`: separate exact `POST_CUTOVER_LOGIC_REVIEWS` and matching check in `phase4a_cutover_contract()`; original hashes, historical counts and event-ID probes remain unchanged. AST comparison confirms every other function, including Phase 1 extraction/retention guards, is identical to the implementation base.
- `test_commission_notice_discovery.py`: eleven election-barometer regressions and the hash-pinned source fixture loader.
- `test_commission_notice_coverage.py`: twelve complete-evidence, literal-score, parser-status and protected-hash regressions.
- `.github/workflows/update-polls.yml`: run the new coverage test class in the existing test step; no trigger or production command change.
- `fr27_commission_barometer_review.json`: two exact notice reviews, 23 complete source table transcriptions, all matched event IDs, distinct bases and the original-source hashes. No polling admission or correction decisions.
- `test_fixtures/fr27_polling/commission_barometer_documents.json.gz`: two new frozen original-document text extracts with explicit PDF identities/hashes; no pre-existing fixture edited.
- `docs/commission_barometer_classifier.md`: this report.

`git diff --check` passed. The complete binary-capable patch passed `git apply --check` against the pristine implementation-base archive. Every existing tracked file was compared with that archive: only the six intended tracked files differ. No production polling JSON, generated page, candidacy file, historical fixture or previous reviewed registry changed. The final production code matches the disposable publication copy exactly.

The pull request contains exactly the nine reviewed files listed above. Primary and existing development worktrees were not modified by this task. The original review artifacts remain in `barometer-validation/commission-barometer-complete.patch`, `final-git-status.txt` and `hygiene-validation.json`; those files describe the pre-commit review snapshot. Final rebase, validation and commit evidence is recorded in the PR description and the separate `pre-pr-*` validation artifacts.

No merge, deployment or manual production workflow execution is authorized by this review.
