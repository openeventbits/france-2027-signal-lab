# Resume on ASUS — Windows PowerShell

Run in a regular Windows terminal. Git Bash executable tests can fail inside a restricted sandbox with `NtCreateDirectoryObject ... 0xC0000022`; do not weaken tests to avoid that error. No command below merges, dispatches a workflow or publishes. Do not run broad suites automatically merely to recreate the already preserved results.

## Fetch and create independent review worktrees

Choose a new clone location, or inspect an existing clone's uncommitted work first. Do not reset an existing checkout. Run each `worktree add` only if its target directory does not already exist.

```powershell
$recoveryRepo = Join-Path $HOME 'Documents\GitHub\france-2027-signal-lab'
# Only if a clone does not already exist:
git clone https://github.com/openeventbits/france-2027-signal-lab.git $recoveryRepo
git -C $recoveryRepo status --short
git -C $recoveryRepo fetch origin
git -C $recoveryRepo worktree list
git -C $recoveryRepo ls-remote --heads origin 'codex/recovery-*2026-11-13'

$recoveryParent = Split-Path $recoveryRepo
$candidateReview = Join-Path $recoveryParent 'fr27-recovery-candidate-nov13'
$pollsReview = Join-Path $recoveryParent 'fr27-recovery-polls-nov13'
$newsReview = Join-Path $recoveryParent 'fr27-recovery-news-nov13'
git -C $recoveryRepo worktree add --detach $candidateReview a8af897c70dff2ca5ea76ad6951457a07b59ca32
git -C $recoveryRepo worktree add --detach $pollsReview 3f58a50434bbb70defad4bba69cf339be2924639
git -C $recoveryRepo worktree add --detach $newsReview dcd8c2a0700fd04165b5dc7c7667bcce5bafabab
git -C $candidateReview status --short
git -C $pollsReview status --short
git -C $newsReview status --short

gh pr view 340 --repo openeventbits/france-2027-signal-lab
gh pr view 341 --repo openeventbits/france-2027-signal-lab
gh pr view 342 --repo openeventbits/france-2027-signal-lab
```

Each checkout must show its exact SHA from HANDOFF.md and be clean. Inspect current `origin/main` and its differences from tested base `caada6984cdb4719ac2cab5310c4d27b5ac7d093` before proposing any update. Do not incorporate PR #339 or other unfinished branches.

## Optional local prerequisites / narrow checks

Use Python 3.12 for production parity, Git for Windows (including Bash), and Node. The completed local results used Python 3.13.5 and Node 24.13.0. These commands install only a separate local virtual environment; they do not alter production.

```powershell
$recoveryTools = Join-Path $env:LOCALAPPDATA 'fr27-recovery-tools'
py -3.12 -m venv (Join-Path $recoveryTools 'venv')
$recoveryPython = Join-Path $recoveryTools 'venv\Scripts\python.exe'
& $recoveryPython -m pip install pandas lxml pypdf
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
node --version

git -C $candidateReview diff --check caada6984cdb4719ac2cab5310c4d27b5ac7d093..HEAD
git -C $pollsReview diff --check caada6984cdb4719ac2cab5310c4d27b5ac7d093..HEAD
git -C $newsReview diff --check caada6984cdb4719ac2cab5310c4d27b5ac7d093..HEAD

# Optional narrow reproduction, one family at a time:
Set-Location $candidateReview
& $recoveryPython -B -m unittest -v test_candidate_reference.CandidateBilingualReferenceTests
Set-Location $pollsReview
& $recoveryPython -B -m unittest -v test_reviewed_cluster17_source_retention.Cluster17SourceRetentionTests.test_previously_supported_snapshots_preserve_their_authenticated_corpora test_reviewed_cluster17_source_retention.Cluster17SourceRetentionTests.test_old_snapshots_reject_extraction_loss_against_the_current_corpus test_reviewed_cluster17_source_retention.Cluster17SourceRetentionTests.test_old_snapshots_still_reject_runoff_extraction_loss_independently
Set-Location $newsReview
& $recoveryPython -B -m unittest -v test_live_projections.LiveWorkflowTests
```

## Explicitly deferred Polls expansion

This command was stopped after the main 480-test suite passed, under the user's handoff priority. Run only when ready to resume validation; no pass is currently claimed. Keep all historical assertions, manifests, source hashes, later additions and Commission decisions unchanged.

```powershell
Set-Location $pollsReview
& $recoveryPython -B -m unittest -v test_update_polls_contract_runner test_poll_explorer test_poll_pages test_bonnal_source_publication test_cnews_10260_source_publication test_poll_hub_static_links test_route_registry test_search_foundation
```

The exact completed full-suite commands are the first `COMMAND` line in `evidence/candidate-final-suite.log`, `evidence/polls-final-suite.log`, and `evidence/news-after-suite.log`. Candidate requires the normal build/check chain first, as recorded in its `candidate-after-build-*.log` files and `.github/workflows/publish-candidate-family.yml`; use a **separate disposable validation checkout**, not a corrective branch's publication files. Do not commit regenerated outputs to these corrective PRs. The known Paris-midnight failure is preserved separately; do not import #339 to hide it.

The five pre-existing News cross-family counterexamples are listed in `evidence/news-cross-failing-tests.json`, with full raw logs and exact unchanged-baseline parity. They need separate scope/disposition. Do not rewrite frozen static expectations, historical evidence, the Commission correction or Architecture-B/precision sources just to make a suite green.

Drafts remain NO-MERGE. Hosted checks may start automatically from PR creation, but no production workflow dispatch/rerun, merge or deployment is authorized. Review their results on ASUS without blindly rerunning failed production jobs.
