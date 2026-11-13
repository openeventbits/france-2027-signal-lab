"""Local, disposable copies only. Never executes workflow publication steps."""
import argparse, ast, hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
import yaml

p=argparse.ArgumentParser(); p.add_argument('kind'); p.add_argument('phase'); p.add_argument('root'); p.add_argument('--extra',nargs='*'); a=p.parse_args()
ev=Path(__file__).resolve().parent
os.environ.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', TEMP=str(ev/'tmp'), TMP=str(ev/'tmp'))
(ev/'tmp').mkdir(exist_ok=True)
root=Path(a.root)
if a.phase in ('before','after'):
    dest=ev/'validation'/f'{a.kind}-{a.phase}'
    if dest.exists(): raise RuntimeError('Refusing to reuse validation copy')
    shutil.copytree(root,dest,ignore=shutil.ignore_patterns('.git','__pycache__'))
    root=dest
os.chdir(root)
wf={'candidate':'publish-candidate-family.yml','polls':'update-polls.yml','news':'update-news-wire.yml'}[a.kind]
workflow=yaml.safe_load((root/'.github/workflows'/wf).read_text(encoding='utf-8'))
steps=next(iter(workflow['jobs'].values()))['steps']
def run(command,label):
    start=time.monotonic()
    with (ev/f'{a.kind}-{a.phase}-{label}.log').open('w',encoding='utf-8') as log:
        log.write('COMMAND '+repr(command)+'\nCWD '+str(root)+'\n'); log.flush()
        result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        log.write(f'\nEXIT {result.returncode}; ELAPSED {time.monotonic()-start:.3f}s\n')
    print(label,result.returncode,flush=True)
    return result.returncode
if a.kind=='candidate' and a.phase in ('before','after'):
    publication=json.loads((root/'publication_manifest.json').read_bytes())['published_at']
    generation=[['build_candidate_polymarket_history.py','--check'],['build_candidate_youtube_history.py','--check'],['build_candidate_bluesky_history.py','--check'],['build_publication_manifest.py','--published-at',publication],['build_candidate_reference.py','--all-active'],['build_candidate_reference.py','--all-active','--check'],['build_route_registry.py','--effective-date','2026-11-13'],['build_route_registry.py','--check'],['build_search_entrypoints.py'],['build_search_entrypoints.py','--check'],['build_route_registry.py','--effective-date','2026-11-13'],['build_route_registry.py','--check'],['build_search_entrypoints.py','--check'],['build_sitemaps.py'],['build_sitemaps.py','--check'],['build_publication_manifest.py','--check']]
    for i,command in enumerate(generation):
        if run([sys.executable,'-B',*command],f'build-{i:02}'):
            raise SystemExit('generation failed; preserved counterexample')
    step=next(s for s in steps if s['name']=='Build and validate candidate publication')
    suite=step['run'].split('python -B -m unittest -v',1)[1].split('git diff',1)[0]
    args=['-m','unittest','-v',*suite.replace('\\',' ').split()]
elif a.kind=='candidate':
    step=next(s for s in steps if s['name']=='Build and validate candidate publication')
    suite=step['run'].split('python -B -m unittest -v',1)[1].split('git diff',1)[0]
    args=['-m','unittest','-v',*suite.replace('\\',' ').split()]
elif a.kind=='polls':
    step=next(s for s in steps if s['name']=='Test polling production contract')
    args=step['run'].split()[2:]
else:
    step=next(s for s in steps if s['name']=='Run news pipeline tests')
    args=step['run'].replace('\\',' ').split()[2:]
result=run([sys.executable,'-B',*args],'suite')
if a.extra:
    result=run([sys.executable,'-B','-m','unittest','-v',*a.extra],'cross') or result
raise SystemExit(result)
