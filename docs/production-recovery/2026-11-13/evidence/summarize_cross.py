import json,re
from pathlib import Path
p=Path(__file__).resolve().parent
results={}
for name in ('news-after-cross.log','news-baseline-cross-counterexamples.log'):
    source=(p/name).read_text(encoding='utf-8')
    results[name]={
        'ids':re.findall(r'^FAIL: \S+ \(([^\n]+)\)',source,re.M),
        'summary':[x for x in source.splitlines() if x.startswith(('Ran ','FAILED ('))],
        'assertions':[x[:350] for x in source.splitlines() if x.startswith('AssertionError:')],
    }
assert results['news-after-cross.log']['ids']==results['news-baseline-cross-counterexamples.log']['ids']
assert len(results['news-after-cross.log']['ids'])==5
assert results['news-after-cross.log']['assertions']==results['news-baseline-cross-counterexamples.log']['assertions']
(p/'news-cross-baseline-parity.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
