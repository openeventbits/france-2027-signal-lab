"""Commit only the three explicitly authorized corrections; never push/merge."""
import ast,json,subprocess
from pathlib import Path
ev=Path(__file__).resolve().parent
base='caada6984cdb4719ac2cab5310c4d27b5ac7d093'
spec={
 'candidate':('codex/recovery-candidate-localization-2026-11-13',['build_candidate_reference.py','test_candidate_reference.py'],'Fix English polling-range decimal localization'),
 'polls':('codex/recovery-polls-retention-scope-2026-11-13',['test_reviewed_cluster17_source_retention.py'],'Separate historical and current Polls retention test scopes'),
 'news':('codex/recovery-news-schedule-fixture-2026-11-13',['test_live_projections.py'],'Keep synthetic News feed schedules internally consistent'),
}
result={}
for family,(branch,paths,message) in spec.items():
    root=Path(f'C:/Users/Tanya/.codex/worktrees/recovery-{family}-nov13/france-2027-signal-lab')
    prefix=['git','-c',f'safe.directory={root.as_posix()}','-C',str(root)]
    def git(*args): return subprocess.check_output(prefix+list(args),stderr=subprocess.STDOUT).decode('utf-8')
    assert git('rev-parse','origin/main').strip()==base
    assert git('rev-parse','HEAD').strip()==base
    assert set(git('diff','--name-only','HEAD').splitlines())==set(paths)
    assert not git('diff','--cached','--name-only').strip()
    assert not git('ls-files','--others','--exclude-standard').strip()
    for name in paths: ast.parse((root/name).read_text(encoding='utf-8'))
    git('diff','--check')
    git('switch','-c',branch)
    git('add','--',*paths)
    assert set(git('diff','--cached','--name-only').splitlines())==set(paths)
    git('diff','--cached','--check')
    subprocess.run(prefix+['-c','user.name=Tanya','-c','user.email=297315548+openeventbits@users.noreply.github.com','commit','-m',message],check=True)
    sha=git('rev-parse','HEAD').strip()
    assert set(git('diff','--name-only',base,sha).splitlines())==set(paths)
    assert not git('status','--porcelain=v1').strip()
    result[family]={'branch':branch,'sha':sha,'base':base,'files':paths,'local_path':root.as_posix()}
    (ev/'handoff-commits.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(family,branch,sha,flush=True)
