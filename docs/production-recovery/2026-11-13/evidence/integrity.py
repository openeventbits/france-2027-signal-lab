import ast, hashlib, json, os, subprocess, sys
from pathlib import Path
ev=Path(__file__).resolve().parent
base='caada6984cdb4719ac2cab5310c4d27b5ac7d093'
expected={'candidate':{'build_candidate_reference.py','test_candidate_reference.py'},'polls':{'test_reviewed_cluster17_source_retention.py'},'news':{'test_live_projections.py'}}
results={}
for kind,allowed in expected.items():
    root=Path(f'C:/Users/Tanya/.codex/worktrees/recovery-{kind}-nov13/france-2027-signal-lab')
    def git(*args):
        return subprocess.check_output(['git','-c',f'safe.directory={root.as_posix()}','-C',str(root),*args])
    assert git('rev-parse','HEAD').decode().strip()==base
    changes=set(filter(None,git('diff','--name-only','HEAD').decode().splitlines()))
    assert changes==allowed,(kind,changes)
    assert not git('diff','--cached','--name-only')
    assert not git('ls-files','--others','--exclude-standard')
    subprocess.run(['git','-c',f'safe.directory={root.as_posix()}','-C',str(root),'diff','--check'],check=True)
    tracked=git('ls-files','-z').decode().split('\0')
    # The News baseline copy is never regenerated. Candidate's baseline copy
    # deliberately rebuilds outputs before its workflow-selected test suite.
    before=ev/'validation/news-before'
    manifest={}; protected_changes=[]
    for name in filter(None,tracked):
        path=root/name
        if path.is_file():
            raw=path.read_bytes(); old=(before/name).read_bytes()
            if name not in allowed and raw!=old: protected_changes.append(name)
            manifest[name]=hashlib.sha256(raw).hexdigest()
        if name in allowed: ast.parse((root/name).read_text(encoding='utf-8'))
    assert not protected_changes,protected_changes
    (ev/f'{kind}-working-sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (ev/f'{kind}.diff').write_bytes(git('diff','--binary','HEAD'))
    (ev/f'{kind}-inventory.txt').write_bytes(git('status','--porcelain=v1')+git('diff','--stat','HEAD'))
    results[kind]={'head':base,'changed_files':sorted(changes),'tracked_files_hashed':len(manifest),'protected_files_identical':len(manifest)-len(changes),'staged':[],'untracked':[],'syntax':'PASS','diff_check':'PASS'}
(ev/'integrity-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
