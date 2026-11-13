import contextlib,io,os,sys,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
sys.path.insert(0,os.getcwd())
import build_candidate_reference as r
ev=Path(__file__).resolve().parent
before=json.loads((ev/'candidate-artifacts-before.json').read_bytes())
after=json.loads((ev/'candidate-artifacts-after.json').read_bytes())
assert before.keys()==after.keys()
changed=[p for p in before if before[p]!=after[p]]
assert all(p.startswith('en/') and p.endswith('.html') for p in changed),changed
print('SAME-DATE',len(before),'artifacts;',len(changed),'English-only changes',changed,flush=True)
for name in changed:
    old=(ev/'candidate-artifacts-before'/name).read_text(encoding='utf-8')
    new=(ev/'candidate-artifacts-after'/name).read_text(encoding='utf-8')
    # Every changed byte belongs to a recognized French numeric polling label.
    import re
    expected=re.sub(r'([\d,.]+–[\d,.]+%)( · \d+ hypothes(?:is|es))',
                    lambda m:m.group(1).replace(',','.')+m.group(2),old)
    assert expected==new,name
root=Path.cwd()
# A fresh generated family from the real after-build sequence, isolated in a copy.
copy=ev/'validation/candidate-after'
class Clock(datetime):
    instant=None
    @classmethod
    def now(cls,tz=None):
        return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)
results=[]
for instant in ('2026-11-13T22:59:59+00:00','2026-11-13T23:00:00+00:00'):
    Clock.instant=datetime.fromisoformat(instant)
    stream=io.StringIO()
    with patch.object(r,'datetime',Clock),patch.object(sys,'argv',['build_candidate_reference.py','--root',str(copy),'--all-active','--check']),contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        try: result=r.main()
        except SystemExit as error: result=error.code
    results.append({'utc':instant,'paris_date':Clock.now(r.ZoneInfo('Europe/Paris')).date().isoformat(),'exit':result,'output':stream.getvalue()})
    print(results[-1],flush=True)
assert results[0]['exit']==0,results
assert results[1]['exit']!=0,results
(ev/'candidate-midnight-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('KNOWN MIDNIGHT DEFECT preserved; localization does not repair event-reference clock')
