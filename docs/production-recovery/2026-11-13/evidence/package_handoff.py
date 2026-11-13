"""Package the review-only ASUS handoff; no test, push, merge or dispatch."""
import hashlib,json,re,shutil,subprocess
from pathlib import Path
ev=Path(__file__).resolve().parent
repo='openeventbits/france-2027-signal-lab'
commits=json.loads((ev/'handoff-commits.json').read_bytes())
prs={}
for family,entry in commits.items():
    source=(ev/f'pr-created-{family}.txt').read_text(encoding='utf-8-sig')
    url=re.search(r'https://github.com/[^\s]+/pull/\d+',source).group()
    pr=json.loads(subprocess.check_output(['gh','pr','view',url,'--repo',repo,'--json','number,url,isDraft,headRefOid,headRefName,baseRefName']))
    assert pr['isDraft'] and pr['headRefOid']==entry['sha'] and pr['headRefName']==entry['branch'] and pr['baseRefName']=='main'
    files=json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/pulls/{pr["number"]}/files']))
    assert {f['filename'] for f in files}==set(entry['files'])
    prs[family]=pr
(ev/'handoff-prs.json').write_text(json.dumps(prs,indent=2),encoding='utf-8')
out=ev/'github-handoff/docs/production-recovery/2026-11-13'
evidence=out/'evidence'; evidence.mkdir(parents=True,exist_ok=True)
for source in ev.iterdir():
    if source.is_file() and source.suffix in {'.log','.json','.txt','.diff','.md','.py'}:
        shutil.copyfile(source,evidence/source.name)
# Raw logs are copied without transformations. Their original hashes must hold.
pins=json.loads((ev/'original-log-sha256.json').read_bytes())
assert all(hashlib.sha256((evidence/name).read_bytes()).hexdigest()==pin for name,pin in pins.items())
incident=(ev/'INCIDENT_REPORT.md').read_text(encoding='utf-8')
incident=incident.replace(ev.as_posix()+'/', '').replace('RUNNING / incomplete','INCOMPLETE / deferred by handoff request')
incident='> Investigation checkpoint before authorized preservation commits. **Read [the final handoff](../HANDOFF.md) for current branches, SHAs, PRs, changed main and deferred gates.** The historical authorization/state statements below describe that earlier checkpoint.\n\n'+incident
(evidence/'INCIDENT_REPORT.md').write_text(incident,encoding='utf-8')
rows='\n'.join(f"| {family.title()} | `{x['branch']}` | `{x['sha']}` | [#{prs[family]['number']}]({prs[family]['url']}) — draft / NO-MERGE |" for family,x in commits.items())
handoff=f'''# ASUS handoff — France 2027 production recovery

November 13, 2026. **Preservation/review only. All three PRs are draft, WIP / NO-MERGE. No merge, production workflow dispatch/rerun, or production publication was performed. Stop here until further authorization.**

## Remote corrections

| Correction | Branch | Exact commit | PR |
|---|---|---|---|
{rows}

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
'''
(out/'HANDOFF.md').write_bytes(handoff.encode('utf-8'))
resume=r'''# Resume on ASUS — Windows PowerShell

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
git -C $recoveryRepo worktree add --detach $candidateReview [CANDIDATE_SHA]
git -C $recoveryRepo worktree add --detach $pollsReview [POLLS_SHA]
git -C $recoveryRepo worktree add --detach $newsReview [NEWS_SHA]
git -C $candidateReview status --short
git -C $pollsReview status --short
git -C $newsReview status --short

gh pr view [CANDIDATE_PR] --repo openeventbits/france-2027-signal-lab
gh pr view [POLLS_PR] --repo openeventbits/france-2027-signal-lab
gh pr view [NEWS_PR] --repo openeventbits/france-2027-signal-lab
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
'''
for family in commits:
    resume=resume.replace('['+family.upper()+'_SHA]',commits[family]['sha']).replace('['+family.upper()+'_PR]',str(prs[family]['number']))
(out/'RESUME_WINDOWS.md').write_bytes(resume.encode('utf-8'))
# Preserve archived evidence bytes across Windows Git checkouts, including raw
# CRLF and intentional whitespace in original logs. Only this docs subtree is
# affected; no correction branch's attributes are changed.
(out/'.gitattributes').write_bytes(b'* -text\nevidence/** -diff\n')
index={}
for path in out.rglob('*'):
    if path.is_file(): index[path.relative_to(out).as_posix()]={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
(out/'EVIDENCE_INDEX.json').write_bytes(json.dumps(index,indent=2).encode('utf-8'))
print(json.dumps({'package':str(out),'files':len(index)+1,'prs':prs},indent=2))
