import json,subprocess
from pathlib import Path
ev=Path(__file__).resolve().parent
root=Path('C:/Users/Tanya/Documents/GitHub/france-2027-signal-lab')
base='caada6984cdb4719ac2cab5310c4d27b5ac7d093'
spec={
 'candidate':('b4b682d34c81687fac6e8ccb6ad4048c1b7f0c3d',['build_candidate_reference.py','test_candidate_reference.py','.github/workflows/publish-candidate-family.yml']),
 'polls':('b1388b6f7e01ea61a46208f28fb9a285e0bf81bc',['fetch_polls.py','rehearse_fr_poll_migration.py','test_reviewed_cluster17_source_retention.py','run_update_polls_contract_tests.py','test_update_polls_historical_ids.json','.github/workflows/update-polls.yml']),
 'news':('4605dacea144fa7ca44d9a0f946dc0ed4caca7a2',['fetch_news_wire.py','test_live_projections.py','publisher_policy.json','news_sources.json','.github/workflows/update-news-wire.yml']),
}
result={}
for kind,(sha,paths) in spec.items():
    changed=subprocess.check_output(['git','-C',str(root),'diff','--name-only',sha,base,'--',*paths]).decode().splitlines()
    assert not changed,(kind,changed)
    result[kind]={'successful_run_checkout':sha,'failed_run_and_fix_base':base,'verified_unchanged_code_and_contracts':paths}
(ev/'successful-run-source-comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
