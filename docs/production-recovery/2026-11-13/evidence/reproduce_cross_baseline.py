import os,re,subprocess,sys,json
from pathlib import Path
ev=Path(__file__).resolve().parent
text=(ev/'news-after-cross.log').read_text(encoding='utf-8')
ids=re.findall(r'^FAIL: \S+ \(([^\n]+)\)',text,re.M)
assert len(ids)==5,ids
(ev/'news-cross-failing-tests.json').write_text(json.dumps(ids,indent=2),encoding='utf-8')
with (ev/'news-baseline-cross-counterexamples.log').open('w',encoding='utf-8') as log:
    command=[sys.executable,'-B','-m','unittest','-v',*ids]
    log.write(repr(command)+'\n');log.flush()
    result=subprocess.run(command,cwd=ev/'validation/news-before',stdout=log,stderr=subprocess.STDOUT)
    log.write('\nEXIT '+str(result.returncode)+'\n')
print('baseline reproduction exit',result.returncode)
