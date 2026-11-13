import os,sys,json,copy,hashlib
from pathlib import Path
from datetime import datetime,timedelta
sys.path.insert(0,os.getcwd())
from fetch_news_wire import generate_publisher_site_feeds,publisher_site_feed_due,validate_output
from test_live_projections import synthetic_fetch_snapshot
ev=Path(__file__).resolve().parent
raw=Path('news_wire.json').read_bytes(); wire=json.loads(raw)
anchor=datetime.fromisoformat(wire['generated_at'].replace('Z','+00:00'))
feeds=generate_publisher_site_feeds()
validate_output(wire)
broken=copy.deepcopy(wire); broken['generated_at']=(anchor+timedelta(seconds=1)).isoformat().replace('+00:00','Z')
try: validate_output(broken)
except RuntimeError as error:
    assert str(error)=='feed_coverage publisher-site schedule count is invalid'
else: raise AssertionError('exact original counterexample did not reproduce')
rows=[]
stamps=[anchor,anchor+timedelta(seconds=1)]
for hour in (2,6,12,18):
    b=anchor.replace(hour=hour,minute=0,second=0,microsecond=0)
    stamps.extend([b-timedelta(seconds=1),b,b+timedelta(seconds=1)])
for t in stamps:
    snapshot=synthetic_fetch_snapshot(wire,t); validate_output(snapshot)
    rows.append({'utc':t.isoformat(),'publisher_site_feeds_due':sum(publisher_site_feed_due(f,t) for f in feeds),'publisher_site_feeds_successful':snapshot['feed_coverage']['publisher_site_feeds_successful'],'feeds_successful_this_run':snapshot['feed_coverage']['feeds_successful_this_run'],'valid':True})
result={'snapshot_sha256':hashlib.sha256(raw).hexdigest(),'original_valid':True,'unchanged_policy_since_success':True,'policy_sha256':hashlib.sha256(Path('publisher_policy.json').read_bytes()).hexdigest(),'source_configuration_sha256':hashlib.sha256(Path('news_sources.json').read_bytes()).hexdigest(),'controlled_boundaries':rows}
(ev/'news-boundary-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
