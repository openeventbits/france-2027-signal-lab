> Investigation checkpoint before authorized preservation commits. **Read [the final handoff](../HANDOFF.md) for current branches, SHAs, PRs, changed main and deferred gates.** The historical authorization/state statements below describe that earlier checkpoint.

# France 2027 Signal Lab — production workflow recovery

Evidence date: November 13, 2026. All Actions timestamps below are UTC. This report covers local, uncommitted corrections only. No production workflow was dispatched or rerun; no project commit, project push, PR, project merge, or production publication was performed.

## Decision and scope

Three independent patches are retained in detached, disposable worktrees at authenticated main `caada6984cdb4719ac2cab5310c4d27b5ac7d093`. Candidate changes one localization expression plus regression tests. Polls and News change tests only. No historical evidence migration or integrity-check relaxation is required.

The Candidate midnight defect remains reproducible and separate. The localization patch does not establish general production recovery across midnight. News' complete workflow suite passes locally, but its broader cross-family selection has five unchanged-baseline failures; that gate remains NO-GO. Hosted Linux/Python 3.12 validation of these exact future PR revisions remains required before merge; this authorization does not allow creating those revisions or dispatching validation.

## Repository preflight and evidence preservation

The authenticated GitHub connector identified `openeventbits` and returned main at `caada6984cdb4719ac2cab5310c4d27b5ac7d093`. The local CLI credential was invalid. Initial local `origin/main` was `2acb9383006528a7afd4ec4af2369a692c3550bb`; a completed public Git fetch updated it to the same SHA authenticated through GitHub. Subsequent inspection used the authenticated connector for Actions logs. Initial sandbox denial of `.git/FETCH_HEAD` was resolved through the authorized fetch outside the sandbox.

The original checkout was on `codex/campaign-events-2026-11-05`, HEAD `962b436d999ade2ebfb298d5b9e5ac0e2c93c8b8`, clean before work. Existing worktrees and their staged, unstaged and untracked inventories were read without alteration. In particular, the midnight worktree/PR #339, Commission admission draft, News integrity/precision worktrees and other unfinished work were left intact. Each new worktree started directly at authenticated main, with none of those uncommitted changes copied.

Evidence: [preflight-summary.json](preflight-summary.json), [main-history.txt](main-history.txt), [worktrees-initial.txt](worktrees-initial.txt), [worktree-status-inventory.txt](worktree-status-inventory.txt), [run-inventory.json](run-inventory.json), [successful-runs.json](successful-runs.json). The source histories between the last successful and failing Candidate/Polls/News runs have no relevant workflow, validator or test-code changes: data evolution exposed the defects. See [successful-run-source-comparison.json](successful-run-source-comparison.json); the successful checkout SHAs were also confirmed from each job's `git log -1` output. A final authenticated read still returned the same main, with the same latest failing runs; see [latest-actions-inventory.json](latest-actions-inventory.json).

All ten downloaded complete job logs (five cited latest attempts, the earlier Candidate attempt, three successful comparisons, and the original Agenda midnight incident) were saved outside the fix worktrees. SHA-256 of each saved UTF-8 file matches the exact connector text. See [original-log-sha256.json](original-log-sha256.json). The original logs and production artifacts were not edited.

## Actual Actions failures and intentional skips

| Workflow / run | Job ID | Authenticated checkout | Failure |
|---|---:|---|---|
| [Candidate 43151855448, attempt 1](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/43151855448/job/130962670481) | 130962670481 | `42e60ea2cc9e` | 588 tests, one localization failure |
| [Candidate 43151855448, attempt 2](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/43151855448/job/130980865910) | 130980865910 | `42e60ea2cc9e` | 588 tests, one localization failure |
| [Candidate 43349142465](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/43349142465/job/131635653446) | 131635653446 | `caada6984cdb` | 588 tests, one localization failure |
| [Polls 43330091692](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/43330091692/job/131572323875) | 131572323875 | `4605dacea144` | 478 tests, one retention-test scope failure |
| [Polls 43380199519](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/43380199519/job/131735941880) | 131735941880 | `caada6984cdb` | 478 tests, same failure |
| [News 43403609396](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/43403609396/job/131812343504) | 131812343504 | `caada6984cdb` | 473 tests, five schedule-counter fixture failures |

Preserved original failure logs: Candidate [earlier attempt 1](logs-43151855448-attempt1.log), [earlier attempt 2](logs-43151855448.log), [latest](logs-43349142465.log); Polls [earlier](logs-43330091692.log) and [latest](logs-43380199519.log); News [failing run](logs-43403609396.log).

Candidate fails in **Build and validate candidate publication**. Polls fails in **Test polling production contract**, before collection. News fails in **Run news pipeline tests**, before collection. The publication/commit/push/Pages steps following those failures are skipped.

Exact failure signatures:

- Candidate: `test_candidate_reference.CandidateBilingualReferenceTests.test_english_generated_compositional_ui_is_localized`; an English expected polling label is absent because its lower decimal comma survives.
- Polls: `test_reviewed_cluster17_source_retention.Cluster17SourceRetentionTests.test_previously_supported_snapshots_preserve_their_authenticated_corpora`; `"widespread second_round extraction loss" does not match "widespread first_round extraction loss: 284 rows; expected at least 90% of 316"`.
- News: `RuntimeError: feed_coverage publisher-site schedule count is invalid`, in `test_live_projections.LiveWorkflowTests.test_executed_promotion_matches_promoted_source`, `test_executed_semantic_noop_has_zero_projection_churn`, `test_executed_stale_artifact_repair_uses_committed_source`, `test_inventory_bookkeeping_and_stale_repair_preserve_public_snapshot`, and `test_inventory_bookkeeping_preserves_public_snapshot` (the latter four share the same module/class prefix).

Downstream runs such as Candidate `43404182272`, Agenda `43404203582`, Issue `43404203653` after failed News, and Candidate `43381000366` / Agenda `43381000513` / Issue `43381000622` after failed Polls, are intentionally skipped by their upstream-success condition. They are not independent failing workflow executions. Candidate provider collection steps are also intentionally skipped for non-schedule/non-dispatch events. Full inventory and job step conclusions are in [run-inventory.json](run-inventory.json).

Most recent successful comparisons retrieved:

| Family | Run / job | Tests | Comparison |
|---|---|---|---|
| Candidate | [43122255878 / 130865365888](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/43122255878/job/130865365888) | 588, OK | Before the newer fractional lower polling bound |
| Polls | [43244520114 / 131273485039](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/43244520114/job/131273485039) | 478 + 172 publication/search, OK | Baseline before the 360th first-round observation |
| News | [43348541466 / 131633669310](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/43348541466/job/131633669310) | 473, OK | Generated the 01:59:59.882576Z snapshot that exposes the next test's boundary error |

Raw successful logs: [success-43122255878.log](success-43122255878.log), [success-43244520114.log](success-43244520114.log), [success-43348541466.log](success-43348541466.log). Printed `FAILED Broken: RuntimeError: blocked` inside otherwise successful News test logs is an expected injected failure probe; the unittest summary and job conclusion determine suite success.

## Candidate root cause and isolated correction

The recognized compositional label uses `re.fullmatch(r"(.+) · (\d+) hypothèse(?:s)?", value)`. Its nested substitution `(?<=\d),(?=\d+%)` only normalizes the number immediately before `%`. In `30,5–30,5% · 1 hypothèse`, it produces `30,5–30.5% · 1 hypothesis`; the lower comma survives.

The one-line production correction uses `(?<=\d),(?=\d)` **only inside that existing full-match branch and only on its captured numeric-label portion**. It does not introduce a general replacement over HTML, evidence, URLs or source data. Regression cases cover integer bounds, fractional lower/upper/both bounds, and singular/plural labels, including all three requested examples. The unchanged current Marine Le Pen compositional test is included. Unrecognized evidence-like strings remain outside this translation path; rendering preserves the source projection.

Controlled same-date regeneration of the complete family produces 143 artifacts: all 47 data JSON objects and all 48 French HTML files are byte-identical before/after. Overall 139/143 artifacts are identical. The four changed English pages are Marine Le Pen, Marine Tondelier, Nathalie Arthaud and Édouard Philippe. A complete text comparison permits only decimal normalization within the polling-range/hypothesis label. English source-language evidence remains unchanged. Generated copies only were rebuilt; no checked-in artifact was updated.

Evidence: [candidate-artifacts-before.json](candidate-artifacts-before.json), [candidate-artifacts-after.json](candidate-artifacts-after.json), [candidate-boundary-probe.log](candidate-boundary-probe.log). The workflow's generation/check chain includes histories, manifest, all-active dossiers, routes, search entrypoints and sitemaps; its commands and logs are preserved by [validate.py](validate.py) and `candidate-after-build-*.log`.

### Separate midnight defect

Neither attempt of cited run `43151855448` has a midnight test failure: both complete with exactly one localization failure. The separate confirmed incident is [Agenda 42714090288 / job 129497235735](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/42714090288/job/129497235735). Candidate readiness succeeds before Paris midnight and revalidation later rejects `candidates/anasse-kazib/data.json`; see [midnight-42714090288.log](midnight-42714090288.log) and [midnight-evidence.json](midnight-evidence.json).

The local full-family counterexample uses the unchanged live-clock implementation, with only the external test clock controlled. At `2026-11-13T22:59:59Z` (23:59:59 Paris), the corrected generated family checks successfully: 40 FR + 40 EN active dossiers, seven retained archives, two hubs. At `23:00:00Z` (November 14 in Paris), the same source/snapshot fails on Anasse's data JSON. See [candidate-midnight-results.json](candidate-midnight-results.json). This is a retained known defect, not a green midnight publication result. No PR #339 code, workflow pin, date expectation or fallback was imported.

Changed files: `build_candidate_reference.py`, `test_candidate_reference.py`. Diff: [candidate.diff](candidate.diff). Size: 25 insertions, one deletion across two files.

## Polls root cause and scope-explicit correction

The failure is not lost or changed historical polling evidence. The failed assertion is a current-corpus negative control embedded inside a historical-success method; the pinned 326/97 historical success obligation itself remains valid. It is a valid rejection against an expanded current corpus, coupled to a test that expected a later guard to fire first. `reconcile_french_production_source` evaluates first round, then second round; its unchanged rule rejects when `extracted × 10 < expected × 9`.

The early snapshots `240490172`, `240498648`, `240522402` extract 284 first-round and 95 runoff rows. The original retention-review commit `47e7f1f2c458a16e70067929f1d8558779391122` had 349/108 retained objects; its first-round expected count was 305, so first round passed and runoff failed against 106. Current main has 360/111 objects; first-round expected count is 316 after 44 historical-only persistence obligations, and runoff expected count is 109 after two such obligations. `2840 < 2844`, so first round now fails first.

The exact tipping addition is event `42b2db1a5afeb28d8e0d6ce328a3242888274e46422f9aacdf819ef13ddf5c9d`, Cluster17, fieldwork end November 10, added by `57ea0363e27bd5c771a629eda232edac9af682bd`. Before this commit the expected first-round denominator was 315: `2840 >= 2835`, so it reached runoff. The preceding addition `69f7241d24aabd2bf280de440307b81cb09ef98721cb4b11845312165b2674a5` in `86d1b843a2a42abc778d853f6bef37b93c49c060` included Marine Le Pen at 30.5.

All 349 first-round and 108 runoff objects from the original review remain identical in type, field content and array-relative order; current additions are retained. Complete authenticated first-round expansion history:

| Commit | First-round count | Added | Earlier objects changed/removed |
|---|---:|---:|---:|
| `c7206e441494` | 349 → 353 | 4 | 0 |
| `8c27eff3b9ec` | 353 → 358 | 5 | 0 |
| `86d1b843a2a4` | 358 → 359 | 1 | 0 |
| `57ea0363e27b` | 359 → 360 | 1 | 0 |

See [polls-corpus-lineage.json](polls-corpus-lineage.json), [polls-scope-probe.log](polls-scope-probe.log), [probe_polls.py](probe_polls.py). The phase1 326/97 fixture replays successfully and identically against all three early source revisions. Source `240570516` still preserves the complete current corpus. It is deliberately not replayed as a success against pre-review phase1 data: the later Batch 1 authenticated obligations reject that incompatible scope.

The test-only patch keeps the existing phase1 equality assertions and later-current equality assertion unchanged, removes the current-corpus negative assertion from that historical-success method, and adds two independent controls:

1. Each early snapshot must fail the first-round guard against the actual current corpus.
2. Each must independently fail the runoff guard when first round is held to the approved runner's authenticated 337-object selection and runoff remains current. This is an explicitly scoped negative control, not a claim that the mixed test inputs were a published historical snapshot.

The approved runner itself, its three immutable historical methods, its 439-object pins, the 326/97 fixture, all source hashes, finite retention decisions and negative mutations are unchanged. The independent guard probe passes for all three revisions; see [polls-runoff-isolation-final.log](polls-runoff-isolation-final.log). No 90% threshold, production reconciliation, polling value, normalization or Commission registry record changes.

Changed file: `test_reviewed_cluster17_source_retention.py`. Diff: [polls.diff](polls.diff). Size: 22 insertions, four deletions.

## News root cause and fixture-only correction

**A demonstrated; B not demonstrated for this snapshot; C excluded by authenticated code/config comparison.** Current published `news_wire.json` at `2026-11-13T01:59:59.882576Z` validates with 22 publisher-site feeds due. The test advances only `generated_at` to `02:00:00.882576Z`, where policy schedules 35. It retains the old count 22. The validator correctly rejects that internally inconsistent synthetic snapshot. The schedule function uses UTC hour modulo each feed's interval and stable slot; a one-second change can cross an hour boundary even though it appears small.

The real snapshot validates against its own timestamp. The real generator derives scheduled feeds and payload counters from its single supplied `generated_at`. `publisher_policy.json`, `news_sources.json`, the schedule function, validator, workflow and test source did not change between the last success and failure. No policy change or production-counter mismatch is evidenced here.

The test helper now recomputes due counters for its synthetic timestamp, sets synthetic publisher-site successes to zero, and removes the old publisher-site successes from the overall success counter. It does not invent collection successes, alter source statuses for a no-op, or modify the production validator. The existing explicit semantic-change scenario still changes an actual source status and the corresponding success counters.

The exact failing timestamp and controlled UTC boundaries at 02:00, 06:00, 12:00 and 18:00 are validated before/on/after the boundary. Due counts include 22 → 35 at 02:00 and 29 → 19 at noon; equal counts at 06:00 and 18:00 are covered too. All synthetic payloads pass the unchanged validator. See [news-boundary-results.json](news-boundary-results.json) and [news-boundary-probe.log](news-boundary-probe.log).

Executed promotion evidence, using the actual workflow Python block and disposable fixture directories:

| Scenario | Published files changed |
|---|---|
| Valid fetch-only timestamp/counter no-op | None |
| Legitimate source-status change | `news_wire.json`, `agenda/live.json`, `enjeux/live.json` |
| Missing Agenda projection repair | `agenda/live.json` only |
| Invalid Issues projection | None; exact authoritative-source mismatch raised |

Inventory-only bookkeeping and inventory-plus-stale-repair assertions also remain in the original full suite. The failure-atomicity probe checks all nine source/projection files, not only Wire. Evidence: [news-execution-evidence.json](news-execution-evidence.json), [news-execution-probe.log](news-execution-probe.log). No live network collection or production publication was performed by these probes.

Changed file: `test_live_projections.py`. Diff: [news.diff](news.diff). Size: 39 insertions, four deletions. Frozen News precision classifier and Architecture-B oracle sources/expectations are untouched.

## Validation results and limitations

| Gate | Result |
|---|---|
| Candidate unchanged failing test before | 1 tests / 26.526s / FAILED (failures=1) — [raw log](candidate-baseline-targeted.log) |
| Candidate full original local selection before | 588 tests / 1074.200s / FAILED (failures=1, errors=4) — [raw log](candidate-before-suite.log) |
| Candidate final full selection (588 originals + 3 new) | 591 tests / 1581.094s / OK — [raw log](candidate-final-suite.log) |
| Candidate lifecycle/registry/orchestration + Agenda/Issue automation | 116 tests / 350.713s / OK — [raw log](candidate-final-cross.log) |
| Candidate bilingual targeted after | 26 tests / 73.501s / OK — [raw log](candidate-after-targeted.log) |
| Polls unchanged failing test before | 1 tests / 18.732s / FAILED (failures=1) — [raw log](polls-baseline-targeted.log) |
| Polls final production selection (478 originals + 2 new) | 480 tests / 3186.002s / OK — [raw log](polls-final-suite.log) |
| Polls historical-runner mutations + publication/search contracts | INCOMPLETE / deferred by handoff request — [raw log](polls-final-cross.log) |
| News unchanged LiveWorkflowTests before | 8 tests / 38.483s / FAILED (failures=5) — [raw log](news-baseline-targeted.log) |
| News full original local selection before | 473 tests / 690.035s / FAILED (failures=6) — [raw log](news-before-suite.log) |
| News final full selection (473 originals + 1 new) | 474 tests / 1090.079s / OK — [raw log](news-after-suite.log) |
| News Agenda/Issue page/policy/automation contracts | 161 tests / 252.242s / FAILED (failures=5) — [raw log](news-after-cross.log) |
| News additional Agenda page projection contracts | 78 tests / 53.342s / OK — [raw log](news-agenda-pages-cross.log) |
| News exact cross-family failures on unchanged main | 5 tests / 8.309s / FAILED (failures=5) — [raw log](news-baseline-cross-counterexamples.log) |

The original hosted failures remain the authoritative completed baseline workflow results. Local baseline test harness issues are recorded separately: Windows sandbox Git Bash failed with `NtCreateDirectoryObject ... 0xC0000022`; its added local News failure was resolved by running the unchanged shell test outside the sandbox. Initially copied Candidate sources lacked Git metadata, causing four local harness errors in `git show`/`git ls-files` consumers. Disposable copies were given independent HEAD/config/index metadata at authenticated main and read-only access to existing objects, without creating commits or modifying any original index. The final complete Candidate run uses that corrected harness.

Intermediate diagnostic logs are retained, including `news-after-targeted.log` (one sandbox Git Bash failure), an initial Candidate after-run interrupted once its missing-Git harness error was understood, and `polls-after-targeted.log`, whose control prototype used phase1 first round and was rejected by later reviewed retention obligations. The final independent runoff control uses the approved authenticated runner scope instead. Redundant long baseline/prototype runs were interrupted; they are not reported as completed green suites. See [baseline-validation-notes.txt](baseline-validation-notes.txt). Final suite results above are reported separately, without combining partial runs into a fictional green workflow. An incomplete metadata serialization is labeled `actions-inventory.partial.json`; the complete normalized inventories and original job logs are used for conclusions.

Local runtime is Windows/Python 3.13.5 with pandas, lxml, pypdf and Git Bash. UTF-8 and a permitted temporary directory were set for local subprocesses. Existing Agenda race/reconciliation integration tests create commits, merges and local pushes only inside their disposable fixture repositories; their remote is an explicitly local temporary `remote.git`, not GitHub. No project worktree commit or network push occurs. Linux/Python 3.12 is the production workflow runtime; no hosted run of these uncommitted patches exists. WSL access was denied in the sandbox. See [runtime.txt](runtime.txt). Hosted checks must run the exact final PR source, the complete workflow-selected suites, downstream contracts, and final artifact/scope verification before merge. No claim of a green production workflow follows from targeted tests or these local runs alone.

### Additional unchanged-baseline cross-family counterexamples

The News cross-family selection runs 161 tests and has five failures. All five reproduce on the unchanged authenticated main snapshot, with the same assertion signatures; see [news-cross-baseline-parity.json](news-cross-baseline-parity.json) and [news-baseline-cross-counterexamples.log](news-baseline-cross-counterexamples.log). Four are in `test_issue_pages`: `HistoricalIssueDetailRedesignTests.test_locked_source_renders_remain_byte_identical`, and `IssuePageArtifactTests.test_current_hub_html_remains_byte_identical`, `test_historical_detail_pages_match_redesign_source_contract`, `test_rendering_is_deterministic`. They compare current rendering with retained static HTML, including different OG-image revisions and content. The fifth is `test_policy_agenda_frontend.PolicyAgendaFrontendTests.test_poll_compare_is_not_a_workspace`, a current-JavaScript assertion.

These sources and expectations are protected, unchanged files in the News patch. The directly affected live projections and all 474 News workflow tests pass, and the additional 78 Agenda page contracts pass. The larger cross-family gate remains failed. No static artifact was regenerated to conceal it and no expectation was changed. Correcting these additional baseline defects requires separate scope and evidence; this task stops at preserving their counterexamples while continuing the independent Candidate and Polls validation.

## Integrity and unchanged artifacts

All three worktrees remain detached at the same authenticated main. Each has 1,098 tracked files hashed. Candidate has exactly two changed source/test files; Polls and News each have one changed test file. Every other tracked file is byte-identical to the unregenerated preserved baseline: 1,096 protected files for Candidate and 1,097 for each test-only patch. All three have empty staged and untracked inventories, passing AST syntax and `git diff --check`.

The source data, schema definitions, routes, historical fixtures, retained records, normalizations, sitemaps, manifests, published HTML/JSON, source-policy configuration and frozen work are unchanged in the fix worktrees. Rebuilt validation outputs exist only in disposable evidence copies. Candidate's expected future English output differences are documented independently above; they have not been written into a production artifact or the corrective worktree.

| Preserved artifact | Raw SHA-256 in every fix worktree |
|---|---|
| `polls.json` | `57fd407f76b9816bb664154233c19159c359836d773d0b06d3d276781d477805` |
| `second_round_polls.json` | `84b61e0bb6006d1ad1b80da9238871f42da5a6382dcb2dff550d96aa5c658346` |
| `news_wire.json` | `33c66476be7f464647f34f11017a9c7cc5ccbbaeba6343a6636fd5d0125a06f3` |
| `commission_notice_registry.json` | `aefe3fc55c0442600419fe838af982302f5825665a1849778521a231adf2e804` |
| `publication_manifest.json` | `a07f61d01682d2185f8dc6ef76db57656dcfed9ab42c3c6d4801ee63e3d7e0d5` |
| `route_registry.json` | `fcfb013ccf30c158b93214aa638d0323566cef356bde963ba455efb4b4bfedb1` |
| `test_fixtures/fr27_polling/phase1_published_326_97.json.gz` | `ab1736b8edceab85859707a6105a1e14471dec4e680dc217699bbe1acf493446` |
| `test_update_polls_historical_ids.json` | `3d9140fb33ea127ec6814a0291bd8b124aad02630db6e97a38d8aaa17dd6d87a` |

Full manifests and scope evidence: [integrity-results.json](integrity-results.json), [integrity.log](integrity.log), [candidate-working-sha256.json](candidate-working-sha256.json), [polls-working-sha256.json](polls-working-sha256.json), [news-working-sha256.json](news-working-sha256.json), and the three `*-inventory.txt` files. Each diff independently passes `git apply --check` against the unchanged main copy; see [independent-patch-checks.txt](independent-patch-checks.txt). These raw byte hashes are distinct from canonical JSON review digests; the approved runner's canonical manifest pin remains `fdf8509d5b3bd1361ac035d60e48a4113e67f3f5061a082efe9cb00a114d3be3`.

## Review recommendations, merge order and monitoring

Review-readiness and merge-readiness are separate. No incomplete or failing gate is treated as green:

| Corrective PR | Recommendation | Remaining gate |
|---|---|---|
| News synthetic schedule bookkeeping | Isolated fixture fix ready for review; **NO-GO for merge** | Five reproduced baseline cross-family failures require separate disposition, then exact-source hosted Linux/Python 3.12 validation |
| Polls scope-explicit historical/current controls | GO for isolated corrective review | Exact-source hosted production/historical-runner/downstream suites before merge |
| Candidate decimal localization | GO for isolated localization review; NO-GO for claiming midnight recovery | Hosted full Candidate suite; separate midnight remediation remains open |

No merge or production publication is authorized by this report. The unresolved Commission correction and the hosted blockers documented on [PR #339](https://github.com/openeventbits/france-2027-signal-lab/pull/339) remain outside these patches. This task neither migrated those historical expectations nor certified the unrelated general dashboard suite.

Recommended future sequence, conditional on each PR's own gates: Candidate localization first to prepare the shared consumer, Polls scope next, News fixture last after its cross-family block has an approved disposition. Keep each PR separate; a blocked PR must not contaminate or prevent independent review of the others. Re-authenticate latest main before preparing each PR; if source data have advanced, repeat the relevant corpus/schedule counterexamples and integrity checks against that main. Regenerated outputs belong to the normal, separately authorized publication transaction. Midnight remediation requires its own reviewed resolution before claiming complete Candidate recovery; importing unmerged #339 is not part of this sequence.

After separately authorized merges, monitor naturally scheduled writers and their logs read-only. Confirm test gates complete before collection/promotion, actual collected snapshots validate against their own timestamps, and publication artifacts/routes/manifests pass their normal checks. Check that eligible downstream jobs run after success and upstream-failure skips remain intentional. For News, inspect a scheduled run crossing a UTC publisher-slot boundary and a real no-op for zero semantic churn. For Polls, confirm retained IDs/objects and the unchanged 90% guard. For Candidate, inspect the exact English range labels and same-date determinism; explicitly monitor a Paris-midnight transaction and retain any failure evidence until the separate clock defect is resolved. Do not rerun a failure blindly or relax evidence checks to complete publication.

## Reviewable local work

- Candidate: `C:/Users/Tanya/.codex/worktrees/recovery-candidate-nov13/france-2027-signal-lab` — [candidate.diff](candidate.diff)
- Polls: `C:/Users/Tanya/.codex/worktrees/recovery-polls-nov13/france-2027-signal-lab` — [polls.diff](polls.diff)
- News: `C:/Users/Tanya/.codex/worktrees/recovery-news-nov13/france-2027-signal-lab` — [news.diff](news.diff)

All are uncommitted and unstaged. They are retained for independent review, not published or archived away.
