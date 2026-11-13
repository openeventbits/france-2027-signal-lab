import sys, os, json, gzip, subprocess, hashlib
from pathlib import Path
sys.path.insert(0, os.getcwd())
from test_reviewed_cluster17_source_retention import source, typed_json
from fetch_polls import integrate_french_migration_source, load_poll_wave_overrides
from poll_migration import parse_french_frozen_fixture
import run_update_polls_contract_tests as runner

def git(*args):
    return subprocess.check_output(['git', '-c', f'safe.directory={Path.cwd().as_posix()}', *args])
first = json.loads(Path('polls.json').read_bytes())
second = json.loads(Path('second_round_polls.json').read_bytes())['events']
introduced = '47e7f1f2c458a16e70067929f1d8558779391122'
oldfirst = json.loads(git('show', introduced+':polls.json'))
oldsecond = json.loads(git('show', introduced+':second_round_polls.json'))['events']
historical = json.loads(gzip.decompress(Path('test_fixtures/fr27_polling/phase1_published_326_97.json.gz').read_bytes()))
scopes = {'current':(first,second), 'original-review':(oldfirst,oldsecond), 'phase1':(historical['first_round'],historical['second_round'])}
approved = runner.historical_inputs()
scopes['approved-runner'] = (approved['polls.json'], approved['second_round_polls.json']['events'])
for name,(f,s) in scopes.items():
    print('SCOPE',name,len(f),len(s),hashlib.sha256(typed_json((f,s)).encode()).hexdigest(),flush=True)
    for rev in (240490172,240498648,240522402,240570516):
        try:
            result=integrate_french_migration_source(source(rev),f,s,[e for e in f if e.get('official_notice_id')],retain_published_history=True)
            print(name,rev,'SUCCESS',len(result[0]),len(result[1]),'same',typed_json(result[:2])==typed_json((f,s)),flush=True)
        except Exception as error:
            print(name,rev,type(error).__name__,str(error),flush=True)
oldmap={e['event_id']:e for e in oldfirst}
print('ORIGINAL FIRST objects unchanged', all(typed_json(e)==typed_json(next(x for x in first if x['event_id']==e['event_id'])) for e in oldfirst))
print('ORIGINAL SECOND objects unchanged', all(typed_json(e)==typed_json(next(x for x in second if x['event_id']==e['event_id'])) for e in oldsecond))
for rev in ('86d1b843a2a42abc778d853f6bef37b93c49c060','57ea0363e27bd5c771a629eda232edac9af682bd'):
    before=json.loads(git('show',rev+'^:polls.json')); after=json.loads(git('show',rev+':polls.json'))
    ids={e['event_id'] for e in before}; extra=[e for e in after if e['event_id'] not in ids]
    print('COMMIT ADDITIONS',rev,len(before),len(after),[(e['event_id'],e['pollster'],e['fieldwork_end']) for e in extra],flush=True)
