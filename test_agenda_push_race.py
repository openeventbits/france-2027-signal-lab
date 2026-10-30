"""Exercise the production reconciliation shell against two independent Git clones.

Only expensive domain validation is replaced by a deterministic fixture builder.
Fetch/rebase, contract guard, staging, allowlist, push classification/budget and
GITHUB_OUTPUT success/no-op behavior are the actual workflow implementation.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class AgendaPushRaceTests(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.check_output(['git', *args], cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.remote = self.base/'remote.git'
        self.a, self.b = self.base/'publisher', self.base/'merger'
        self.git(self.base, 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.git(self.base, 'clone', str(self.remote), str(self.a))
        for clone in (self.a,):
            self.git(clone, 'config', 'user.name', 'fixture')
            self.git(clone, 'config', 'user.email', 'fixture@example.test')
        (self.a/'agenda').mkdir()
        (self.a/'en/agenda').mkdir(parents=True)
        (self.a/'en/agenda/index.html').write_text('fixture')
        for name in ('agenda_coverage_history.json', 'agenda_pages_manifest.json',
                     'route_registry.json', 'sitemap.xml', 'sitemap-core.xml',
                     'sitemap-candidates.xml', 'sitemap-polls.xml',
                     'sitemap-issues.xml', 'sitemap-agenda.xml'):
            (self.a/name).write_text('fixture')
        (self.a/'agenda/out.txt').write_text('base')
        (self.a/'news_wire.json').write_text('{"value": "base"}')
        (self.a/'ready').write_text('yes')
        self.git(self.a, 'add', '.')
        self.git(self.a, 'commit', '-m', 'base')
        self.git(self.a, 'push', 'origin', 'main')
        self.git(self.base, 'clone', str(self.remote), str(self.b))
        self.git(self.b, 'config', 'user.name', 'merger')
        self.git(self.b, 'config', 'user.email', 'merger@example.test')
        self.initial = self.git(self.a, 'rev-parse', 'HEAD')

    def run_publication(self, collisions=0, mode='normal', noop=False):
        if not noop:
            (self.a/'agenda/out.txt').write_text('local-publication')
            self.git(self.a, 'add', '.')
            self.git(self.a, 'commit', '-m', 'publication')
        workflow = (ROOT/'.github/workflows/publish-agenda-family.yml').read_text(encoding='utf-8')
        block = workflow.split('        id: reconcile\n', 1)[1].split('        run: |\n', 1)[1].split('\n      # GITHUB_TOKEN', 1)[0]
        script = '\n'.join(line[10:] if line.startswith('          ') else line for line in block.splitlines())
        start, end = script.index('# BEGIN reconciliation readiness'), script.index('# END reconciliation readiness')
        script = script[:start] + 'test "$(cat ready)" = yes || { echo "readiness failed" >&2; exit 1; }\n' + script[end:]
        start, end = script.index('read -r published_at'), script.index('git add --')
        # Independent fixture validation on each newly fetched base. Keep the
        # production path guard and commit/push control flow under execution.
        validation = f'''"{sys.executable.replace(chr(92), '/')}" -B "{(self.base/'validate.py').as_posix()}"
git diff --check
assert_allowed_changes
'''
        script = script[:start] + validation + script[end:]
        (self.base/'validate.py').write_text('''import json, pathlib
r=pathlib.Path.cwd()
value=json.loads((r/'news_wire.json').read_text())['value']
if value=='validation-failure': raise SystemExit('fixture validation failed')
if value=='unauthorized': (r/'forbidden.json').write_text('forbidden')
output=value if value != 'base' else ''' + repr('base' if noop else 'local-publication') + '''
(r/'agenda/out.txt').write_text(output)
assert (r/'agenda/out.txt').read_text()==output
with pathlib.Path(''' + repr(str(self.base/'validated')) + ''').open('a') as log: log.write(value+'\\n')
''', encoding='utf-8')
        hook = self.base/'collision.py'
        hook.write_text('''import pathlib, subprocess
base=pathlib.Path('''+repr(str(self.base))+''')
b=base/'merger'
counter=base/'pushes'
n=int(counter.read_text())+1 if counter.exists() else 1
counter.write_text(str(n))
mode='''+repr(mode)+'''
if mode=='auth': raise SystemExit(23)
if n>'''+str(collisions)+''': raise SystemExit(0)
def git(*args): subprocess.run(['git',*args],cwd=b,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
git('pull','--ff-only')
git('checkout','-b','pr-'+str(n))
if mode=='conflict': (b/'agenda/out.txt').write_text('concurrent-output')
elif mode=='contract': (b/'changed_contract.py').write_text('# new contract')
elif mode=='invalid': (b/'news_wire.json').write_text('invalid JSON')
elif mode=='readiness': (b/'ready').write_text('no')
elif mode in ('validation-failure','unauthorized'): (b/'news_wire.json').write_text('{"value": "'+mode+'"}')
elif mode=='applied':
    (b/'agenda/out.txt').write_text('local-publication')
    (b/'news_wire.json').write_text('{"value": "upstream-1"}')
else: (b/'news_wire.json').write_text('{"value": "upstream-'+str(n)+'"}')
git('add','.')
git('commit','-m','concurrent PR '+str(n))
git('checkout','main')
git('merge','--no-ff','pr-'+str(n),'-m','merge concurrent PR '+str(n))
git('push','origin','main')
with (base/'concurrent').open('a') as f: f.write(subprocess.check_output(['git','rev-parse','HEAD'],cwd=b,text=True))
''', encoding='utf-8')
        wrapper = f'''git() {{
if [[ "$1" == push ]]; then
  "{sys.executable.replace(chr(92), '/')}" -B "{hook.as_posix()}" || {{ echo 'authentication failed' >&2; return 23; }}
fi
command git "$@"
}}
'''
        env = dict(os.environ, RUNNER_TEMP=str(self.base), GITHUB_OUTPUT=str(self.base/'output'))
        bash = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'Git/bin/bash.exe') if os.name=='nt' else shutil.which('bash')
        result = subprocess.run([bash], input='set -euo pipefail\n'+wrapper+script, cwd=self.a, env=env, text=True, capture_output=True, timeout=60)
        self.output = (self.base/'output').read_text() if (self.base/'output').exists() else ''
        self.pushes = int((self.base/'pushes').read_text()) if (self.base/'pushes').exists() else 0
        self.validated = (self.base/'validated').read_text().splitlines() if (self.base/'validated').exists() else []
        return result

    def assert_recovered(self, collisions, mode='normal'):
        result = self.run_publication(collisions,mode)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('pushed=true', self.output)
        self.assertEqual(self.pushes, collisions+1)
        self.assertEqual(self.validated, ['base']+[f'upstream-{i}' for i in range(1,collisions+1)])
        tip = self.git(self.remote, 'rev-parse', 'main')
        self.assertEqual(self.git(self.remote, 'show', 'main:agenda/out.txt'), f'upstream-{collisions}')
        self.assertEqual(self.git(self.remote, 'show', 'main:news_wire.json'), '{"value": "upstream-'+str(collisions)+'"}')
        for commit in (self.base/'concurrent').read_text().splitlines():
            self.git(self.a, 'merge-base', '--is-ancestor', commit, tip)

    def test_concurrent_pr_merge_recovers_with_updated_inputs(self): self.assert_recovered(1)
    def test_second_collision_also_recovers(self): self.assert_recovered(2)
    def test_already_applied_commit_does_not_amend_upstream(self): self.assert_recovered(1,'applied')

    def test_failed_validation_suppresses_push_and_pages(self):
        r=self.run_publication(1,'validation-failure')
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.pushes,1)
        self.assertIn('fixture validation failed',r.stderr)
        self.assertNotIn('pushed=true',self.output)

    def test_unauthorized_generated_path_stops(self):
        r=self.run_publication(1,'unauthorized')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Unexpected path after reconciliation',r.stderr)
        self.assertNotIn('pushed=true',self.output)

    def test_readiness_barriers_stay_equivalent(self):
        s=(ROOT/'.github/workflows/publish-agenda-family.yml').read_text(encoding='utf-8')
        first=s.split('id: candidate_readiness',1)[1].split("<<'PY'\n",1)[1].split('\n          PY',1)[0]
        retry=s.split('# BEGIN reconciliation readiness',1)[1].split("<<'PY'\n",1)[1].split('\n          PY',1)[0]
        self.assertEqual(retry, first+'\n          if not ready:\n              raise SystemExit("Candidate readiness failed after reconciliation")')

    def test_repeated_collisions_exhaust_budget_without_pages(self):
        r=self.run_publication(3)
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.pushes,3)
        self.assertIn('budget exhausted',r.stderr)
        self.assertNotIn('pushed=true',self.output)
        self.assertEqual(self.git(self.remote,'show','main:agenda/out.txt'),'base')

    def test_conflict_aborts_without_overwriting_either_commit(self):
        r=self.run_publication(1,'conflict')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('reconciliation conflict',r.stderr)
        self.assertEqual(self.git(self.remote,'show','main:agenda/out.txt'),'concurrent-output')
        self.assertEqual(self.git(self.a,'show','HEAD:agenda/out.txt'),'local-publication')
        self.assertNotIn('pushed=true',self.output)
        self.assertFalse((self.a/'.git/rebase-merge').exists())

    def test_invalid_reconciled_input_stops(self):
        r=self.run_publication(1,'invalid')
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.pushes,1)
        self.assertNotIn('pushed=true',self.output)

    def test_changed_contract_stops_before_rebase(self):
        r=self.run_publication(1,'contract')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Publication contract changed',r.stderr)
        self.assertNotIn('pushed=true',self.output)

    def test_readiness_is_rechecked(self):
        r=self.run_publication(1,'readiness')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('readiness failed',r.stderr)
        self.assertNotIn('pushed=true',self.output)

    def test_unrelated_push_failure_is_not_retried(self):
        r=self.run_publication(mode='auth')
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.pushes,1)
        self.assertIn('other than a non-fast-forward',r.stderr)
        self.assertNotIn('pushed=true',self.output)

    def test_noop_never_pushes_or_requests_pages(self):
        r=self.run_publication(noop=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.pushes,0)
        self.assertIn('pushed=false',self.output)
        self.assertEqual(self.git(self.remote,'rev-parse','main'),self.initial)

    def test_production_readiness_and_validation_are_inside_retry(self):
        s=(ROOT/'.github/workflows/publish-agenda-family.yml').read_text(encoding='utf-8')
        retry=s.split('for publication_attempt in 0 1 2; do',1)[1]
        self.assertIn('Candidate readiness failed after reconciliation',retry)
        self.assertIn('stored != expected',retry)
        self.assertIn('test_production_publication_queue',retry)
        self.assertIn('cmp "$RUNNER_TEMP/agenda-rebased-first.sha256"',retry)
        self.assertIn('steps.reconcile.outputs.pushed == \'true\'',retry)
