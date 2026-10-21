# FR27 polling accuracy corrections - Batch 1 final review

Implemented in the existing isolated `codex/polling-accuracy-batch1` worktree from base `155bc87b6b14d8ef0b9ed71af377db5c8f6f54cf`. The primary checkout and tracked production data remain unchanged. This report records the completed factual validation and final pre-PR verification; commit, normal push and PR creation were subsequently authorized by the user. Merge, deployment and manual production workflow execution remain outside that authorization.

## Final two corrections

**Ifop Hollande configuration:** decision `FR27-B1-E` corrects Nicolas Dupont-Aignan from 2.5% to 2%, taking the total from 100.5% to 100%. All nine candidate-score entries were verified against the original individual table (PDF p13 / printed p11). The canonical event ID remains `9f33fd416a66b1ed0a57260cd84fbe566de7763c32ac5aca10287dff04cbc30f`. Its exact predecessor and corrected objects, PDF hash, page references, accepted old/corrected discovery representations and review reason are recorded in the existing Batch 1 registry. No other Ifop configuration changes.

**Commission notice 10324:** coverage changes from `unresolved / ambiguous_published_waves` to `reconciled / reviewed_notice_complete_configurations`. Recognition requires the exact notice ID, an explicitly reviewed resolved URL, the original PDF SHA-256, institute, publication date, fieldwork dates and first-round scope, plus the complete exact six-event collection. All six matched event IDs are retained as coverage evidence. The five historical 1701/reported representations and the sixth 1553/registered-voter representation are left intact. Missing, duplicate, extra or changed configurations, or mismatched notice identity/hash/provenance, retain an unresolved warning. This does not claim an automatic parser or change general coverage equivalence.

Compared with the previously validated Batch 1 outputs, only the Hollande event changes: all **436 other published objects**, including all five runoff successors, are exactly unchanged. The eight original A-D decisions and all existing fixtures remain unchanged. Every other Commission notice object is exactly unchanged; the other **12 unresolved notices** remain unresolved.

## Exact changed files and functions

The final two corrections modify only these five files relative to the validated Batch 1 working state:

| File | Change |
| --- | --- |
| `fr27_polling_accuracy_batch1.json` | Append `FR27-B1-E`; add the exact notice 10324 coverage decision with all six complete configuration objects and original-document provenance. The existing eight decisions are unchanged. |
| `reviewed_polling_accuracy.py` | Update the reviewed bundle digest; existing `reconcile_batch1_accuracy` applies the compatible ninth score decision unchanged. New `reconcile_batch1_notice_coverage` validates the exact notice and complete configuration evidence after ordinary coverage, then updates only notice 10324. |
| `fetch_polls.py` | `main` calls the bounded notice review after generic coverage, only for the live French path; frozen fixture execution is unchanged. |
| `test_polling_accuracy_batch1.py` | Preserve prior regressions, update their now-resolved score/count expectations, and add six regressions for exact score-only correction, source reversal, notice identity, full configuration coverage, incomplete/changed/extra evidence, and historical no-op behavior. There are now 21 Batch 1 tests. |
| `docs/polling_accuracy_batch1.md` | This final evidence, identity, validation and hygiene report. |

The cumulative Batch 1 diff also retains the earlier changes to `.github/workflows/update-polls.yml`, `poll_migration.py`, `rehearse_fr_poll_migration.py`, and the three new fixtures `batch1_original_tables.json`, `batch1_pre_review_333_102.json.gz`, and `fr_mediawiki_240562307.json.gz`. Those six files are not changed by the final two corrections.

The protected `poll_contract.py`, `commission_notice_discovery.py` and `commission_notice_coverage.py` remain unchanged, as do the prior first-round correction/expansion registries and the ten-decision runoff evidence registry. The Phase 1 extraction floor, immutability and diagnostic logic are unchanged.

## Primary evidence

Pages below are one-based. Original PDF bytes, extracted text and page renders are retained in the sibling validation artifacts. Complete independent table transcriptions are in `test_fixtures/fr27_polling/batch1_original_tables.json`; its original pre-review discrepancy note is historical and is now resolved by decision E.

- [Elabe Commission notice 10324](https://www.commission-des-sondages.fr/notices/files/notices/2026/octobre/10324-pres-iv-elabe-17-octobre.pdf): methodology pp1/6; six individual first-round configurations pp7-8. Configuration 4 (Arthaud 1%) and configuration 6 (Polony 1.5%) are on p8. SHA-256 `a8a95533cad304be016080af5960ec928c8a6d4c49089e6c11b851feb4f235d8`.
- [Elabe original report](https://elabe.fr/fichier-pdf/13329-les-francais-et-lelection-presidentielle-2027/): methodology p2, recap p7, configuration 4 p16, configuration 6 p20. SHA-256 `edbb125fd84f90b26fe6d98e8e42563ca0e876fb46804e23937e99d2e1dd8f99`.
- [Ifop-Fiducial original results](https://www.ifopgroup.com/wp-content/uploads/2026/10/122853-barometre-de-lelection-presidentielle-vague-7-resultats-densemble.pdf): methodology PDF p4 / printed p2; eight individual first-round tables PDF pp9-16 / printed pp7-14; Hollande table PDF p13 / printed p11; Ruffin-Polony table PDF p16 / printed p14; runoff recap PDF p18 / printed p16 and individual tables PDF pp19-23 / printed pp17-21. SHA-256 `fec8e2405fc1cc8523908d8ef70e738585021fc4ce6161195e0c8e6c2fdee7bd`.
- [Ifop original publication](https://www.ifopgroup.com/?p=96858), published 20 October: registered-voter sample and fieldwork from 17 October at 20h through 19 October.

### Complete corrected/admitted first-round tables

**FR27-B1-A** - Elabe 2026-10-14 to 2026-10-16.

| Candidate | % |
| --- | --- |
| Nathalie Arthaud | 1 |
| Jean-Luc Mélenchon | 16 |
| Fabien Roussel | 1.5 |
| Raphaël Glucksmann | 16.5 |
| Gabriel Attal | 9.5 |
| Bruno Retailleau | 9 |
| Nicolas Dupont-Aignan | 2.5 |
| Marine Le Pen | 31 |
| Éric Zemmour | 3.5 |
| François Ruffin | 3 |
| David Lisnard | 6.5 |

Total: 100.0%.

**FR27-B1-B** - Elabe 2026-10-14 to 2026-10-16.

| Candidate | % |
| --- | --- |
| Nathalie Arthaud | 1 |
| Fabien Roussel | 1 |
| Jean-Luc Mélenchon | 15 |
| Marine Tondelier | 2.5 |
| Raphaël Glucksmann | 16 |
| Natacha Polony | 1.5 |
| Édouard Philippe | 16.5 |
| Bruno Retailleau | 7.5 |
| Nicolas Dupont-Aignan | 2.5 |
| Marine Le Pen | 33.5 |
| Éric Zemmour | 3 |

Total: 100.0%.

**FR27-B1-C** - Ifop 2026-10-17 to 2026-10-19.

| Candidate | % |
| --- | --- |
| Nathalie Arthaud | 0.5 |
| Jean-Luc Mélenchon | 15 |
| Fabien Roussel | 2 |
| François Ruffin | 2 |
| Marine Tondelier | 3 |
| Raphaël Glucksmann | 12 |
| Gabriel Attal | 6 |
| Édouard Philippe | 12 |
| Bruno Retailleau | 6 |
| Nicolas Dupont-Aignan | 2 |
| Marine Le Pen | 35 |
| Éric Zemmour | 3.5 |
| Natacha Polony | 1 |

Total: 100.0%.

**FR27-B1-E** - Ifop 2026-10-17 to 2026-10-19.

| Candidate | % |
| --- | --- |
| Nathalie Arthaud | 0.5 |
| Jean-Luc Mélenchon | 20 |
| François Hollande | 10 |
| Gabriel Attal | 6.5 |
| Édouard Philippe | 14 |
| Bruno Retailleau | 6 |
| Nicolas Dupont-Aignan | 2 |
| Marine Le Pen | 38 |
| Éric Zemmour | 3 |

Total: 100.0%.

## Identity and explicit lineage

A and E retain their event IDs because scores and sample metadata do not participate in the deterministic event hash. Their exact predecessor/corrected objects and dedicated `reviewed_correction_id` record the approved factual changes. D dates participate in identity: the five successors retain their deterministic new IDs and `supersedes_event_id` lineage. No additional event is superseded by the final two corrections. Unrecognized prior/successor objects, both predecessor and successor IDs, alternative-ID configuration duplicates and conflicting source representations fail closed.

| Decision | Predecessor ID | Corrected/admitted ID |
| --- | --- | --- |
| FR27-B1-A | `fa50fd467626dce418bbdf33a5c859235e51b6b7d5d67158e0eb5a13b9bac856` | `fa50fd467626dce418bbdf33a5c859235e51b6b7d5d67158e0eb5a13b9bac856` |
| FR27-B1-B | None - official admission | `ba337267d959ac63155184f6a4554fee3076b0186ca14e6259b0f76d13648d90` |
| FR27-B1-C | None - official admission | `458cb1a84a083ed5be2c5275b0e20fe0988fab911b9090ae7a5cc0611b4f642e` |
| FR27-B1-D-Jean-Luc Mélenchon | `a233b6b1c77d00740286c6bfc74c97472e2ee359c6dc5288028259106c419139` | `115ff210edfe581876a9fae703475ecec7f608b2312df5d2ce64941e7ec4117a` |
| FR27-B1-D-Raphaël Glucksmann | `ed3b0944c6e298e66eb3d9ffd1d1c173af598b862105153901dcf3702428c26a` | `3e337be6f1827ed917ec83139951a27de24713fbc93cb0249150b7f9ebf08677` |
| FR27-B1-D-Édouard Philippe | `2bc03248b8380b8f6d9c388b9dd2d1f0cfddc1c46bc2506fce2aceef326a9311` | `ca79c8681e49e780251417d6d916c3d5df2cbabefa17d3a831a978ee148aa553` |
| FR27-B1-D-Gabriel Attal | `e90cc39c2cb9b055f44514b654f46831cc3e69d3d480b5fa4d57d920d94d988c` | `e97f8a9a7ba535b47a0b2c191562fa86bbcf8e38ee904d213a5b180541c62d88` |
| FR27-B1-D-François Hollande | `0c13045c50fa51f5ee0dcd59e01fc24aee555cfbe3246315dc042a1ea249bf4f` | `dc48e1acd3d243666e98420673a25411d08adb73f2ef7375632e52f548be17a2` |
| FR27-B1-E | `9f33fd416a66b1ed0a57260cd84fbe566de7763c32ac5aca10287dff04cbc30f` | `9f33fd416a66b1ed0a57260cd84fbe566de7763c32ac5aca10287dff04cbc30f` |

Notice 10324 matches exactly these six reviewed published IDs:

- `5ff49eb542f9bf3d36d1d373a75293825bf1642f78ccd9b52b7d8e09bca6a23a`
- `63aecb7f3bd59f50845e47dc628ed7d480330d1a028228561ad2cc6a3bb1afb0`
- `7ee19ced363715b4348b5ea26a9ebaf3bf8b543484a57213b497f874ef486149`
- `ba337267d959ac63155184f6a4554fee3076b0186ca14e6259b0f76d13648d90`
- `e8c6a9220ec0addb6bdb9e4370d871ee7d788f04d06bf5e54caadf0aa28d6f51`
- `fa50fd467626dce418bbdf33a5c859235e51b6b7d5d67158e0eb5a13b9bac856`

## Counts and sample semantics

| Group | Before original Batch 1 | Final |
| --- | ---: | ---: |
| First-round events | 333 | 335 |
| Elabe 14-16 October configurations | 5 | 6 |
| Ifop 17-19 October configurations | 7 | 8 |
| Runoff events | 102 | 102 |
| Target Ifop runoff observations | 5 through 20 October | 5 through 19 October |

All six Elabe and eight Ifop first-round tables now agree with their original individual tables and total 100%. The dash for Arthaud in Ifop configuration 6 is represented as zero only for comparison with its existing source record; no positive support is inferred.

- B uses `sample_size=1553`, `sample_scope=registered_voters`: the registered-voter subsample extracted from 1701 Elabe adults. Expressed voting intentions further filter for likelihood of voting; no exact expressed/likely-voter denominator is invented.
- C and all five D successors use `sample_size=1928`, `sample_scope=registered_voters`, extracted from 2081 Ifop adults. No matchup-specific count is documented or manufactured.
- A, E and the historical sibling configurations preserve their prior sample representations. In particular, the historical Elabe 1701/reported values describe the adult survey sample, not a precise voting-intention denominator. The new coverage review recognizes only the exact verified survey collection without rewriting those samples.
- Polony remains a hypothetical polling option in these records. The independent candidacy-status registry is unchanged.

## Validation

Final outputs and logs are in the sibling `batch1-final-validation` directory. The original Batch 1 artifacts remain separately preserved in `batch1-validation`.

- Focused final suite: **58/58 passed**, including all 21 Batch 1 tests, 16 existing Commission coverage tests and 21 Phase 1 ingestion stability tests.
- Full polling/publication suite: **907/907 main tests passed** (838.208s) plus **210/210 additional tests passed** (69.674s), **1117 total** across 30 modules. Modules and complete logs are retained in the validation directory.
- Two production-equivalent temporary fetches: **both exited 0**; first-round bytes, runoff event objects/semantics, closest-runoff semantics, and Commission registries are identical. The first starts from the previously validated Batch 1 corpus, and the second consumes its corrected outputs.
- Downstream publication generation/checks: **19/19 passed**: 335 scenarios across 79 waves, eight featured Ifop hypotheses, 158 bilingual poll pages, both hubs, 322 routes, search, sitemaps, closest-runoff status `agree`, and manifest snapshot `bf8e70f19e564d5d06afa12984232c4f66491ecad40d8e3a9a01e79e79e7b6f1`.
- Exact before/after object and notice checks: compared with validated Batch 1, only event `9f33fd416a66b1ed0a57260cd84fbe566de7763c32ac5aca10287dff04cbc30f` and notice 10324 change. All 436 other published objects and every other notice object are exactly unchanged.
- Cumulative original-history continuity: 428 unrelated original events remain exactly unchanged; only the same five explicitly reviewed D predecessors disappear. A and E retain their original IDs.
- All original frozen fixtures and protected logic hashes remain intact. The coverage review is inactive for pre-review snapshots and the live-fetch hook excludes frozen fixture runs.

## Remaining limits and review status

No factual conflict remains in the six Elabe or eight Ifop configurations reviewed here. The five legacy Elabe sample representations remain historical data; they have not been silently normalized. The other 12 unresolved Commission notices remain unchanged and outside this patch.

At the factual-validation checkpoint, all work was uncommitted in the original isolated worktree. `final.diff` contains that complete cumulative Batch 1 patch; `incremental.diff` contains only the final two corrections relative to the validated working state; `final-status.txt` and the hygiene report record that checkpoint's repository status.

## Final pre-PR verification

Fetched and verified `origin/main` at `8d44d60ac982b97a324244917ede598517f8a12d`. Its four intervening commits refresh news, candidate, agenda and issue outputs (131 files). None overlaps the 11 Batch 1 files or changes polling inputs, contracts, correction registries, implementation, tests or frozen fixtures. Current main's 333 first-round and 102 runoff objects exactly match the frozen pre-review corpus. Candidate-signal polling fields are unchanged.

The complete cumulative patch matches the previously validated patch and applies cleanly to a temporary archive of current main. No rebase, reset or changes to existing worktrees were needed. Only this report was updated after that comparison. The three added fixtures are intentional evidence snapshots; no existing fixture, production dataset or generated publication output is included in the patch.

Reused the validated **1117/1117 full-suite tests** and **two production-equivalent temporary fetches**, since the implementation and polling inputs have not changed. Against current main plus Batch 1, freshly reran **58/58 focused tests** (121.997s), including all nine decisions, repeat ingestion, five runoff supersessions, complete-evidence coverage failures and Phase 1 stability. Then overlaid the verified temporary polling outputs in that disposable copy and reran **19/19 downstream publication generation/check commands**, including candidate signals, polling pages, closest-runoff consumers, routes, search, sitemaps and publication manifest. All passed; the same 12 out-of-scope notices remain unresolved.

Final `git diff --check`, exact file allowlist, historical-fixture and protected-file checks passed. Validation artifacts are retained outside the implementation worktree in the sibling `batch1-pre-pr-validation` directory. No implementation adjustment was necessary for newer main.
