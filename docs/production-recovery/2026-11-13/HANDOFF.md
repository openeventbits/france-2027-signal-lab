# ASUS handoff — France 2027 production recovery

November 13, 2026. **Preservation/review only. All three PRs are draft, WIP / NO-MERGE. No merge, production workflow dispatch/rerun, or production publication was performed. Stop here until further authorization.**

## Remote corrections

| Correction | Branch | Exact commit | PR |
|---|---|---|---|
| Candidate | `codex/recovery-candidate-localization-2026-11-13` | `a8af897c70dff2ca5ea76ad6951457a07b59ca32` | [#340](https://github.com/openeventbits/france-2027-signal-lab/pull/340) — draft / NO-MERGE |
| Polls | `codex/recovery-polls-retention-scope-2026-11-13` | `3f58a50434bbb70defad4bba69cf339be2924639` | [#341](https://github.com/openeventbits/france-2027-signal-lab/pull/341) — draft / NO-MERGE |
| News | `codex/recovery-news-schedule-fixture-2026-11-13` | `dcd8c2a0700fd04165b5dc7c7667bcce5bafabab` | [#342](https://github.com/openeventbits/france-2027-signal-lab/pull/342) — draft / NO-MERGE |

These are three independent commits, each directly based on authenticated/tested main `caada6984cdb4719ac2cab5310c4d27b5ac7d093`. Candidate changes only `build_candidate_reference.py` and `test_candidate_reference.py`; Polls changes only `test_reviewed_cluster17_source_retention.py`; News changes only `test_live_projections.py`. The PR file lists and exact head SHAs were read back from GitHub and verified. All three local worktrees are clean after committing.

Evidence is isolated on `codex/recovery-handoff-2026-11-13`. **Do not merge this evidence branch into a corrective PR.** It contains this handoff, Windows resume instructions and archived logs/diffs/manifests; no correction code is mixed into it.

## Main advanced before push

The final fetch found main at `b4f737c0ba577e3225b3cc8b1c7d9b1672340759`:

- `f80ea1dcf3e2f388e5612286391691aee54d3c95` — Update Claims Under Scrutiny.
- `b4f737c0ba577e3225b3cc8b1c7d9b1672340759` — Update candidate attention data.

Only five generated/input artifacts changed: `candidate_attention.json`, `candidate_signals.json`, `claims_under_scrutiny.json`, `publication_manifest.json`, `recent_changes.json`. No corrected file overlaps, so there is no textual conflict in the independent patches. **The branches were deliberately not rebased or broadly retested against the newer input state.** Revalidate compatibility on ASUS before any merge. No production data was changed to obtain passing tests.

## Completed and incomplete gates

Local runtime: Windows / Python 3.13.5; production is hosted Linux / Python 3.12. No exact-commit hosted result is certified here. Opening drafts may start normal repository CI automatically; no workflow was manually dispatched or rerun. Do not automatically investigate or fix new broad-CI failures under this handoff authorization.

| Correction | Completed | Remaining / NO-MERGE reason |
|---|---|---|
| Candidate | **591/591 production tests**, **116/116 cross-family tests**. Complete build/check chain passed. Same-date full-family comparison: 139/143 artifacts identical; four English polling labels differ, all 47 JSON + 48 French HTML artifacts identical. | Separate Paris-midnight defect remains: full-family check passes at 22:59:59Z and fails at 23:00:00Z on Anasse's data JSON. No PR #339 code imported. New-main and hosted validation pending. |
| Polls | **480/480 production tests**, including all three immutable authenticated historical methods. Original 326/97 success assertions unchanged; current-corpus and independent runoff rejection controls pass. | The additional historical-runner mutation/publication/search expansion was automatically queued by the earlier command, then stopped under the user's new handoff priority. **Partial / incomplete, not green.** Finish it only when resuming. New-main and hosted validation pending. |
| News | **474/474 production tests** (473 original + one boundary regression), **78/78 Agenda page tests**. Executed no-op changed no published files; status change changed Wire + both live projections; invalid projection changed none of nine files. | Broader cross-family selection: **161 tests / 5 failures**. Exact five reproduce on unchanged main (**5/5 fail**, identical assertions). New-main and hosted validation pending. |

News baseline failures are four `test_issue_pages` static-render/artifact expectations and `test_policy_agenda_frontend.PolicyAgendaFrontendTests.test_poll_compare_is_not_a_workspace`. They were preserved, not repaired by changing expectations or artifacts. See [exact signatures/parity](evidence/news-cross-baseline-parity.json).

Polls root cause: old snapshots extract 284 first-round rows; approved additions made the unchanged guard's denominator 316, so first round fails before runoff. The 360th observation in `57ea0363e27bd5c771a629eda232edac9af682bd` tipped the ordering. No 90% guard or production code changed. All 349/108 objects from the original review preserve typed facts and relative order; all 11 later first-round additions are retained.

News root cause: the real 01:59:59.882576Z snapshot validates with 22 site feeds due; advancing only its timestamp one second crosses a UTC slot boundary where 35 are due. The fix changes only synthetic bookkeeping, recomputes due counts, and claims zero synthetic site successes. Policy/configuration and the production validator remain unchanged.

## Resume on ASUS

Follow [Windows commands](RESUME_WINDOWS.md). Start by fetching, checking the exact remote heads above, and inspecting current main; do not blindly reset, rebase, alter historical data, or rerun production workflows. No additional broad cycles were launched for handoff. The final queued Polls expansion is explicitly deferred rather than represented as passing.

Remaining work is limited to review/current-main compatibility, the deferred Polls downstream checks, hosted validation, and separately scoped disposition of the existing midnight/Issue/frontend/Commission blockers. **Do not touch PR #339, the frozen Commission correction or News precision / Architecture-B sources or expectations.** No merge or deployment is authorized. Each PR may be reviewed independently; do not combine patches to conceal failed gates.

## Evidence and local fallbacks

- [Full investigation checkpoint](evidence/INCIDENT_REPORT.md), [exact original log hashes](evidence/original-log-sha256.json), [unchanged-data/scope verification](evidence/integrity-results.json).
- [Candidate full suite](evidence/candidate-final-suite.log), [Candidate cross-family](evidence/candidate-final-cross.log), [Polls full suite](evidence/polls-final-suite.log), [Polls incomplete expansion](evidence/polls-final-cross.log), [News full suite](evidence/news-after-suite.log), [News failing cross-family](evidence/news-after-cross.log), [unchanged-main reproduction](evidence/news-baseline-cross-counterexamples.log).
- [Three exact commits/paths](evidence/handoff-commits.json), [GitHub draft verification](evidence/handoff-prs.json), [Candidate diff](evidence/candidate.diff), [Polls diff](evidence/polls.diff), [News diff](evidence/news.diff).
- Original computer evidence: `C:/Users/Tanya/.codex/visualizations/2026/11/13/01a1d45d-5a0f-74b2-b594-767de3ca9b51/recovery`.
- Local worktrees: `C:/Users/Tanya/.codex/worktrees/recovery-candidate-nov13/france-2027-signal-lab`, `.../recovery-polls-nov13/france-2027-signal-lab`, `.../recovery-news-nov13/france-2027-signal-lab`.

All ten complete original Actions logs remain byte-identical to the retrieved UTF-8 text. Archived incomplete diagnostic logs are labeled by the handoff/test notes and are not counted as passing results. The inventory's `.partial.json` file is a retained incomplete serialization, not an authoritative result.

## Shutdown / storage confirmation

All essential work for this recovery is preserved on GitHub: the three correction commits and draft PRs, this report, ASUS instructions, complete production-suite logs, documented failed/deferred gates, all ten original Actions logs, diffs and evidence inventories. **No essential raw test log is local-only.** The `EVIDENCE_INDEX.json` inventory records the uploaded files and SHA-256 hashes.

Large, reproducible generated working copies were intentionally not uploaded. They are not required to resume from ASUS; their manifests and relevant result logs are uploaded. Optional local caches remain at:

- `C:/Users/Tanya/.codex/visualizations/2026/11/13/01a1d45d-5a0f-74b2-b594-767de3ca9b51/recovery/validation/` (disposable validation checkouts).
- `C:/Users/Tanya/.codex/visualizations/2026/11/13/01a1d45d-5a0f-74b2-b594-767de3ca9b51/recovery/candidate-artifacts-before/`.
- `C:/Users/Tanya/.codex/visualizations/2026/11/13/01a1d45d-5a0f-74b2-b594-767de3ca9b51/recovery/candidate-artifacts-after/`.

The original three local worktrees and the complete local evidence directory are also retained. Unrelated frozen worktrees were left untouched and were not incorporated into these corrections. No further local test process is needed for this handoff. Codex may be closed and the Zenbook shut down; resume review from the verified remote branches on ASUS. This is not merge or deployment approval.
