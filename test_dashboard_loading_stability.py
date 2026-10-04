"""Deterministic URL, ledger validation/readiness, and published Media contracts.

The companion loading-stability.mjs tests actual FR/EN DOM, faults and geometry.
"""
import copy
import json
from pathlib import Path
import re
import subprocess
import unittest

from test_what_changed_localization import run_harness, payload, WHAT_CHANGED_HARNESS
from build_search_entrypoints import construct_semantic_model, MEDIA_START, MEDIA_END

ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / 'index.html').read_text(encoding='utf8')
HYBRID = (ROOT / 'assets/hybrid-dashboard.js').read_text(encoding='utf8')


def function(source, name, indent):
    match = re.search(r'^' + ' ' * indent + r'function ' + name + r'\([^\n]*\) \{.*?^' + ' ' * indent + r'\}', source, re.M | re.S)
    if not match:
        raise AssertionError('Function boundary missing: ' + name)
    return match.group()


def node(code, data=None):
    program = 'const input=JSON.parse(require("fs").readFileSync(0,"utf8"));\n' + code
    result = subprocess.run(['node', '-e', program], cwd=ROOT, input=json.dumps(data), capture_output=True, text=True, encoding='utf8')
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class DashboardLoadingStabilityTests(unittest.TestCase):
    def hash_result(self, pathname, query='', hash_value=''):
        return node('''
          const window={location:{pathname:input.path,search:input.query,hash:input.hash},
            history:{replaceState(_state,_title,url){const next=new URL(url,"https://example.test/");window.location={pathname:next.pathname,search:next.search,hash:next.hash};}}};
          const views={candidates:{hash:"#signal-candidates"},issues:{hash:"#signal-issues"}};
          const hashToView=new Map([["#signal-candidates","candidates"],["#signal-issues","issues"]]);const defaultView="candidates";
        ''' + function(HYBRID, 'resolveSignalViewFromHash', 2) + '''
          resolveSignalViewFromHash();console.log(JSON.stringify(window.location));
        ''', {'path':pathname,'query':query,'hash':hash_value})

    def test_english_path_preserved(self):
        self.assertEqual(self.hash_result('/en/')['pathname'], '/en/')

    def test_english_query_and_hash_preserved(self):
        self.assertEqual(self.hash_result('/en/', '?x=1', '#signal-issues'), {'pathname':'/en/','search':'?x=1','hash':'#signal-issues'})

    def test_french_path_preserved(self):
        self.assertEqual(self.hash_result('/', '?x=1')['pathname'], '/')

    def test_missing_invalid_and_valid_hashes_stay_in_language(self):
        for language in ['/', '/en/']:
            for query in ['', '?x=1']:
                for hash_value in ['', '#invalid', '#signal-candidates', '#signal-issues']:
                    result=self.hash_result(language,query,hash_value)
                    self.assertEqual((result['pathname'],result['search']), (language,query))
                    self.assertEqual(result['hash'],hash_value if hash_value.startswith('#signal-') else '#signal-candidates')

    def test_ledger_snapshot_survives_initial_loading_both_languages(self):
        for language in ['fr','en']:
            result=run_harness(locale=language,state='loading',recent_changes=None)
            self.assertTrue(result['publishedRetained'])
            self.assertEqual(result['empty'], [])
            self.assertEqual(result['busy'], 'true')

    def test_ledger_failure_retains_published_evidence(self):
        for language in ['fr','en']:
            result=run_harness(locale=language,state='error',recent_changes=None)
            self.assertTrue(result['publishedRetained'])
            self.assertEqual(result['empty'], [])
            self.assertEqual(result['busy'], 'false')
            self.assertTrue(result['status'])

    def test_valid_empty_ledger_renders_true_empty(self):
        for language,expected in [('fr','Aucune évolution récente'),('en','No update was identified in the last 14 days.')]:
            result=run_harness(locale=language,recent_changes={'window':{'days':14,'end_date':'2026-09-07'},'items':[]})
            self.assertFalse(result['publishedRetained'])
            self.assertEqual(result['empty'],[expected])

    def test_independent_single_flight_loaders(self):
        start=INDEX.index('    let recentChangesRequest = null;')
        end=INDEX.index('    const electionClockTargets',start)
        result=node('''
          const calls=[],resolvers={};const dashboardState={loadState:{recentChanges:"loading",news:"loading"}};
          const fetch=(url)=>{calls.push(url);return new Promise(resolve=>resolvers[url]=resolve)};
          const validateRecentChangesPayload=x=>x,validateNewsWirePayload=x=>x;
          function setupSignalTabs(){};let newsWirePayload;
          const el={textContent:"",innerHTML:""};const $=()=>el;
          const document={documentElement:{dataset:{}},querySelectorAll:()=>[],querySelector:()=>el};
          function markDataset(name,status,payload){dashboardState.loadState[name]=status;dashboardState[name]=payload;}
          const translate=(_key,fallback)=>fallback,escapeHtml=x=>x;
          function populateCandidateCoverageSelector(){}function renderElectionNews(){}function renderCampaignAgenda(){}
          function renderCandidateCoverage(){}function renderNewsWire(){}function renderSignalDeskNote(){}
        '''+INDEX[start:end]+'''
          (async()=>{
           const a=loadRecentChanges(),b=loadRecentChanges(),c=loadNewsWire(),d=loadNewsWire();
           resolvers['recent_changes.json']({ok:true,json:async()=>({last_successful_check_at:'published'})});
           const recent=await a;const beforeNews=dashboardState.loadState.news;
           resolvers['news_wire.json']({ok:false,status:503});await c;
           console.log(JSON.stringify({calls,sameRecent:a===b,sameNews:c===d,recent,beforeNews,states:dashboardState.loadState}));
          })();
        ''')
        self.assertEqual(result['calls'],['recent_changes.json','news_wire.json'])
        self.assertTrue(result['sameRecent'] and result['sameNews'])
        self.assertEqual(result['beforeNews'],'loading')
        self.assertEqual(result['states'],{'recentChanges':'loaded','news':'error'})
        self.assertIsNotNone(result['recent'])

    def test_recent_schema_validates_without_news(self):
        data=json.loads((ROOT/'recent_changes.json').read_text(encoding='utf8'))
        result=node('const safeSourceUrl=x=>/^https?:/.test(x)?x:"";'+''.join(function(INDEX,n,4) for n in ['ledgerNormalizeText','ledgerParseDate','ledgerParisDateKey','validateRecentChangesPayload'])+'console.log(JSON.stringify(validateRecentChangesPayload(input).items.length));',data)
        self.assertEqual(result,len(data['items']))

    def test_recent_factual_validation_still_rejects_malformed_payloads(self):
        original=json.loads((ROOT/'recent_changes.json').read_text(encoding='utf8'))
        variants=[]
        for field,value in [('schema_version',999),('source_universe',[' Same ','Same']),('source_universe',['Same','Same']),('window',{'days':0}),('items',[{}])]:
            item=copy.deepcopy(original);item[field]=value;variants.append(item)
        for mutate in [
            lambda x:x['items'][0].update(trusted_change_date_kind='invalid'),
            lambda x:x['items'][0]['primary_source'].update(url='javascript:alert(1)'),
            lambda x:x['items'][0].update(supporting_source_count=999),
            lambda x:x.update(newest_trusted_change_at='1900-01-01'),
            lambda x:x['window'].update(start_date='2099-01-01'),
            lambda x:x['items'][1].update(id=x['items'][0]['id']),
        ]:
            item=copy.deepcopy(original);mutate(item);variants.append(item)
        outcomes=node('const safeSourceUrl=x=>/^https?:/.test(x)?x:"";'+''.join(function(INDEX,n,4) for n in ['ledgerNormalizeText','ledgerParseDate','ledgerParisDateKey','validateRecentChangesPayload'])+'''console.log(JSON.stringify(input.map(x=>{try{validateRecentChangesPayload(x);return false}catch{return true}})));''',variants)
        self.assertTrue(all(outcomes))

    def test_news_provenance_is_secondary_and_scoped(self):
        result=node(function(INDEX,'recentChangesProvenance',4)+'''const p={source_universe:["A","B"]};console.log(JSON.stringify([recentChangesProvenance(p,null),recentChangesProvenance(p,{feed_coverage:{direct_feeds:2}}),recentChangesProvenance(p,{feed_coverage:{direct_feeds:1}})]));''')
        self.assertEqual(result,['pending','matched','mismatch'])

    def test_unrelated_lane_cannot_recreate_ledger(self):
        body=function(INDEX,'markDataset',4)
        result=node('''
          let renders=0;const dashboardState={loadState:{},updatedAt:{}};
          function renderMastheadMetadata(){}function renderContextStrip(){}function reconcileRecentChangesProvenance(){}
          function renderWhatChanged(){renders++}const document={dispatchEvent(){}};class CustomEvent{}
        '''+body+'''markDataset("polls","loaded",{});markDataset("claims","loaded",{});markDataset("news","loaded",{});console.log(JSON.stringify(renders));''')
        self.assertEqual(result,0)

    def test_repeat_ledger_render_preserves_entries_and_listeners(self):
        script=WHAT_CHANGED_HARNESS.replace('const filters = byClass', """const first = list.children[0];
          const listeners = [...first.listeners.values()].reduce((n,x)=>n+x.length,0);
          renderWhatChanged();renderWhatChanged();
          if(first!==list.children[0])throw new Error("Ledger recreated");
          if(listeners!==[...first.listeners.values()].reduce((n,x)=>n+x.length,0))throw new Error("Listeners duplicated");
          ledgerSourceIconState.status = "ready";renderWhatChanged();
          const iconReady = list.children[0];
          if(first===iconReady)throw new Error("Owned icon readiness ignored");
          renderWhatChanged();
          if(iconReady!==list.children[0])throw new Error("Ready icons trigger duplicate rendering");
          const filters = byClass""")
        result=subprocess.run(['node','-e',script],cwd=ROOT,input=json.dumps({'href':'https://example.test/','state':'loaded','recentChanges':payload(),'polls':{'events':[]},'claims':{'reviews':[]}}),text=True,encoding='utf8',capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_media_generated_snapshots_exist_in_both_languages(self):
        for file in ['index.html','en/index.html']:
            text=(ROOT/file).read_text(encoding='utf8');region=text[text.index(MEDIA_START):text.index(MEDIA_END)]
            self.assertIn('data-fr27-semantic-snapshot="true"',region)
            self.assertEqual(len(re.findall(r'class="top-media-coverage-row"',region)),20)
            self.assertNotIn('fr27-skeleton',region)
            self.assertIn('role="status"',region)

    def test_media_failure_retains_content_without_destructive_render(self):
        # Fault behavior and retained DOM identity are exercised by the browser matrix.
        body=function(HYBRID,'renderTopMediaPulse',2)
        self.assertLess(body.index('model.state === "unavailable"'),body.index('topMediaMount.innerHTML'))
        self.assertNotIn('topMediaMount.innerHTML',function(HYBRID,'renderAll',2))

    def test_media_status_localized_and_quiet(self):
        body=function(HYBRID,'updateTopMediaStatus',2)
        self.assertIn('aria-busy',body)
        for language in ['fr','en']:
            result=node('const window={};require("vm").runInNewContext(require("fs").readFileSync("locales/"+input+".js","utf8"),{window});'+"""
              const status={textContent:""},topMediaMount={dataset:{},setAttribute(){}};
              const document={getElementById:()=>status};const state={candidateSignals:{status:"loading"}};
              const translate=(key,fallback)=>window.FR27_LOCALES[input][key]||fallback;
            """+body+"""
              updateTopMediaStatus({state:"loading"});const loading=status.textContent;
              updateTopMediaStatus({state:"unavailable"});const failure=status.textContent;
              updateTopMediaStatus({state:"ready"});const comparison=status.textContent;
              console.log(JSON.stringify({loading,failure,comparison}));
            """,language)
            self.assertTrue(all(result.values()))
            self.assertIn('indisponible' if language=='fr' else 'unavailable',result['failure'])
            self.assertIn('Comparaison' if language=='fr' else 'comparison',result['comparison'])
            self.assertNotIn('loading_status.',json.dumps(result))

    def test_media_snapshot_reuses_runtime_model_and_math(self):
        signals=json.loads((ROOT/'candidate_signals.json').read_text(encoding='utf8'))
        changes=json.loads((ROOT/'recent_changes.json').read_text(encoding='utf8'))
        model=construct_semantic_model(signals,changes)['media']
        self.assertEqual(model['fr']['facts']['counts'],model['en']['facts']['counts'])
        self.assertEqual(model['fr']['comparison'],signals['active_field_visibility'])
        for language,file in [('fr','index.html'),('en','en/index.html')]:
            region=(ROOT/file).read_text(encoding='utf8').split(MEDIA_START)[1].split(MEDIA_END)[0]
            for count in model[language]['facts']['counts']:
                self.assertIn(f'<strong>{count}</strong>',region)

    def test_media_init_and_tabs_are_idempotent(self):
        self.assertIn('if (window.hybridDashboard) return;',HYBRID)
        self.assertIn('if (boundMediaTabs.has(tab)) return;',function(HYBRID,'bindTopMediaTabs',2))
        self.assertIn('renderedMediaNews === dashboardState.news',function(HYBRID,'renderTopMediaPulse',2))


if __name__=='__main__':
    unittest.main()
