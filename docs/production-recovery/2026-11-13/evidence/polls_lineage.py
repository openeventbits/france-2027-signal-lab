import json,subprocess
from pathlib import Path
root=Path('C:/Users/Tanya/.codex/worktrees/recovery-polls-nov13/france-2027-signal-lab')
ev=Path(__file__).resolve().parent
def git(*args): return subprocess.check_output(['git','-c',f'safe.directory={root.as_posix()}','-C',str(root),*args])
commits=git('log','--format=%H','--reverse','47e7f1f2c458a16e70067929f1d8558779391122..caada6984cdb4719ac2cab5310c4d27b5ac7d093','--','polls.json').decode().splitlines()
result=[]
for sha in commits:
    before=json.loads(git('show',sha+'^:polls.json')); after=json.loads(git('show',sha+':polls.json'))
    by_id={e['event_id']:e for e in before}; now={e['event_id']:e for e in after}
    added=[e for e in after if e['event_id'] not in by_id]
    changed=[i for i in by_id.keys()&now.keys() if by_id[i]!=now[i]]
    result.append({'commit':sha,'before':len(before),'after':len(after),'changed_existing':changed,'removed':sorted(by_id.keys()-now.keys()),'additions':[{'event_id':e['event_id'],'pollster':e['pollster'],'fieldwork_end':e['fieldwork_end']} for e in added]})
assert sum(len(x['additions']) for x in result)==11
assert not any(x['changed_existing'] or x['removed'] for x in result)
(ev/'polls-corpus-lineage.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
parity={}
for name in ('polls.json','second_round_polls.json'):
    old=json.loads(git('show','47e7f1f2c458a16e70067929f1d8558779391122:'+name))
    now=json.loads((root/name).read_bytes())
    if isinstance(old,dict): old=old['events']; now=now['events']
    ids={e['event_id'] for e in old}
    selected=[e for e in now if e['event_id'] in ids]
    typed=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'))
    assert typed(selected)==typed(old)
    parity[name]={'authenticated_original_objects':len(old),'typed_objects_and_relative_order_identical':True}
(ev/'original-review-object-parity.json').write_text(json.dumps(parity,indent=2),encoding='utf-8')
