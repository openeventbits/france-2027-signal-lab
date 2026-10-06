"""Retained locale ownership and shared control publication contracts.

Real geometry, disclosure, focus and delayed-response tests live in the companion
responsive-forensics global-ui-consistency.mjs browser suite.
"""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

HARNESS = r'''
const fs=require('fs'), vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const root={lang:'fr',dataset:{siteRoot:'/'}};
const canonical={href:'https://france2027.app/'};
const alternate={fr:{href:'https://france2027.app/'},en:{href:'https://france2027.app/en/'}};
const events=[], history=[];
const document={documentElement:root,readyState:'loading',baseURI:'https://example.test/',
 getElementById:id=>input.dashboard&&id==='hybrid-signal-board'?{}:null,
 querySelector:s=>s==='base'?{}:s.includes('hreflang="en"')?alternate.en:s.includes('hreflang="fr"')?alternate.fr:s.includes('canonical')?{setAttribute(_name,value){canonical.href=value;}}:null,
 querySelectorAll:()=>[],addEventListener(){},dispatchEvent(e){events.push({locale:e.detail.locale,api:window.FR27I18N.locale});}};
const window={document,location:new URL('https://example.test/?probe=1#signal-issues'),console,
 addEventListener(){},history:{pushState(_s,_t,href){window.location=new URL(href);history.push(href);}},fetch(){throw Error('Unexpected refetch');}};
class CustomEvent{constructor(type,options){this.type=type;this.detail=options.detail;}}
const ctx={window,globalThis:window,URL,URLSearchParams,Intl,CustomEvent};
for(const name of ['locales/en.js','locales/fr.js'])vm.runInNewContext(fs.readFileSync(name,'utf8'),ctx);
let source=fs.readFileSync('assets/localization.js','utf8').replace('  const api = Object.freeze({','  global.__setLocale = setDashboardLocale;\n  const api = Object.freeze({');
vm.runInNewContext(source,ctx);
const api=window.FR27I18N, pendingCommit=()=>api.t('signal_board.policy_issues');
window.__setLocale('en');const en={locale:api.locale,title:pendingCommit(),url:window.location.href,canonical:canonical.href};
window.__setLocale('fr');const fr={locale:api.locale,title:pendingCommit(),url:window.location.href,canonical:canonical.href};
process.stdout.write(JSON.stringify({en,fr,events,history,identity:api===window.FR27I18N,lang:root.lang}));
'''


def run_locale(dashboard=True):
    result = subprocess.run(['node', '-e', HARNESS], cwd=ROOT,
                            input=json.dumps({'dashboard': dashboard}),
                            capture_output=True, text=True, encoding='utf-8', check=True)
    return json.loads(result.stdout)


class GlobalUIConsistencyTests(unittest.TestCase):
    def test_pending_canonical_data_commit_reads_current_language(self):
        result = run_locale()
        self.assertEqual(result['en']['title'], 'Policy Issues')
        self.assertEqual(result['fr']['title'], 'Enjeux politiques')
        self.assertEqual(result['events'], [{'locale': 'en', 'api': 'en'}, {'locale': 'fr', 'api': 'fr'}])

    def test_dashboard_locale_retains_api_query_hash_and_canonical_routes(self):
        result = run_locale()
        self.assertTrue(result['identity'])
        self.assertEqual(result['en']['url'], 'https://example.test/en/?probe=1#signal-issues')
        self.assertEqual(result['fr']['url'], 'https://example.test/?probe=1#signal-issues')
        self.assertEqual(result['en']['canonical'], 'https://france2027.app/en/')
        self.assertEqual(result['fr']['canonical'], 'https://france2027.app/')
        self.assertEqual(result['lang'], 'fr')

    def test_family_pages_keep_native_document_navigation(self):
        result = run_locale(False)
        self.assertEqual(result['history'], [])
        self.assertEqual(result['events'], [])
        self.assertEqual(result['en']['locale'], 'fr')

    def test_dashboard_workflow_covers_shared_controls_and_mobile_locale_runtime(self):
        workflow = (ROOT / '.github/workflows/publish-dashboard.yml').read_text(encoding='utf-8')
        for name in ['assets/fr27-ui.css', 'assets/tier2-layout.js', 'assets/tier3-layout.js', 'assets/localization.js',
                     'assets/dashboard-navigation.js', 'assets/dashboard-navigation.css',
                     'assets/hybrid-dashboard.js', 'build_search_entrypoints.py']:
            self.assertIn('      - "' + name + '"', workflow)


if __name__ == '__main__':
    unittest.main()
