import os,sys,json,hashlib,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,os.getcwd())
import test_live_projections as t
ev=Path(__file__).resolve().parent
original=subprocess.run
paths=('news_inventory.json','news_wire.json','news_corpus_ledger.json','recent_changes.json','source_health.json','candidate_visibility_history.json','candidate_agenda_history.json','agenda/live.json','enjeux/live.json')
mode=''; records=[]
def capture(*args,**kwargs):
    root=Path(kwargs['cwd'])
    def census():
        return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() if (root/p).is_file() else None for p in paths}
    before=census(); result=original(*args,**kwargs); after=census()
    changed=[p for p in paths if before[p]!=after[p]]
    records.append({'mode':mode,'returncode':result.returncode,'changed_files':changed,'stdout':result.stdout,'stderr':result.stderr})
    if mode=='invalid':
        assert 'issues live projection differs from authoritative source snapshot' in result.stderr
        assert not changed,changed
    elif mode=='noop': assert not changed,changed
    elif mode=='semantic': assert {'news_wire.json','agenda/live.json','enjeux/live.json'}<=set(changed)
    elif mode=='stale': assert changed==['agenda/live.json'],changed
    return result
t.LiveWorkflowTests.setUpClass()
with patch.object(t.subprocess,'run',side_effect=capture):
    for mode,opts in [('noop',{}),('semantic',{'semantic_change':True}),('stale',{'missing':True}),('invalid',{'invalid':True})]:
        t.LiveWorkflowTests().run_promotion(**opts)
(ev/'news-execution-evidence.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print(json.dumps(records,indent=2))
