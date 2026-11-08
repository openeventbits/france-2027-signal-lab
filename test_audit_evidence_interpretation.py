"""November 2 audit: visible interpretation, complete UTC days, source dates."""
import copy
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from build_candidate_signals import _round_visibility_ratio
from fetch_news_wire import build_candidate_visibility
from test_frontend_facts import function_body
from test_news_change_integrity import DUPONT_AIGNAN_2017

ROOT = Path(__file__).resolve().parent


def js(source, expression):
    return json.loads(subprocess.check_output(
        ['node', '-e', source + '\nconsole.log(JSON.stringify(' + expression + '));'],
        cwd=ROOT, encoding='utf-8'))


class AuditEvidenceTests(unittest.TestCase):
    def test_responsive_refresh_keeps_media_popover_attached(self):
        source = (ROOT / 'assets/tier2-layout.js').read_text(encoding='utf-8')
        function = function_body(source, 'restoreMediaOutsideTier2', 'ensureWorkspaceControl')
        for tier3 in (True, False):
            result = js('''let moves = 0;
const mediaPanel = {};
const contextStrip = {nextElementSibling:mediaPanel, insertAdjacentElement(){moves++;}};
const mediaHome = {nextSibling:mediaPanel, parentNode:{insertBefore(){moves++;}}};
let mediaRow = null;
const restoreTabbedMedia = ()=>{};
const tier3Query = {matches:''' + str(tier3).lower() + '};\n' + function,
                '(()=>{restoreMediaOutsideTier2(false);restoreMediaOutsideTier2(false);return moves;})()')
            self.assertEqual(result, 0)

    def test_spotlight_places_qualified_window_by_scores(self):
        source = (ROOT / 'index.html').read_text(encoding='utf-8')
        hero = source[source.index('function renderAgreedRunoff('):source.index('function renderUnresolvedRunoff(')]
        self.assertIn('runoff-window-context', hero)
        self.assertIn('runoff_workspace.qualifying_window', hero)
        for lang in ('fr', 'en'):
            self.assertIn('runoff_workspace.qualifying_window', (ROOT / f'locales/{lang}.js').read_text(encoding='utf-8'))

    def test_non_direct_poll_differences_are_neutral_and_visible(self):
        source = (ROOT / 'index.html').read_text(encoding='utf-8')
        functions = function_body(source, 'formatRaceComparableMagnitude', 'renderBars')
        functions = r'''const translate = (k,f,p={})=>f.replace(/\{(\w+)\}/g,(_,k)=>p[k]??'');
const formatComparableDelta = v => v>0?'+'+v:String(v);
const raceFieldworkRange = (s,e)=>s+'–'+e;
const formatScore = v=>v+'%';
''' + functions
        for classification in ('DIRECT', 'FIELD_CHANGED', 'POLLSTER_CHANGED', 'POLLSTER_AND_FIELD_CHANGED'):
            result = js(functions, 'formatRacePreviousPollDifference(' + json.dumps({
                'classification': classification, 'delta': -1.5, 'currentScore':33.5, 'previousScore':35,
                'current':{'pollster':'Ipsos'}, 'previous':{'pollster':'Harris'}, 'sameField':True}) + ')')
            self.assertIn('-1.5 pts', result['value'])
            if classification != 'DIRECT':
                self.assertEqual(result['tone'], 'is-contextual')
                self.assertTrue(result['visibleContext'])
            else:
                self.assertEqual(result['tone'], 'is-negative')
        for classification in ('NO_PRIOR', 'AMBIGUOUS_PRIOR'):
            self.assertEqual(js(functions, f'formatRacePreviousPollDifference({{classification:"{classification}"}})')['value'], '—')

    def test_seven_day_periods_exclude_incomplete_generation_day(self):
        for timestamp in ('2026-11-02T00:00:00+00:00', '2026-11-02T23:59:59+00:00', '2026-11-02T01:00:00+02:00'):
            generated = datetime.fromisoformat(timestamp)
            result = build_candidate_visibility([], generated)
            expected_end = '2026-10-31' if generated.astimezone(timezone.utc).day == 1 else '2026-11-01'
            self.assertEqual(result['current_period']['end_date'], expected_end)
            self.assertIsNone(result['comparison_quality']['record_count_ratio'])

    def test_verified_tf1_date_is_corrected_without_mutating_observation(self):
        from news_publication_corrections import reviewed_publication_entry
        item = copy.deepcopy(DUPONT_AIGNAN_2017)
        item['published_at'] = datetime.fromisoformat('2026-10-24T06:00:57+00:00')
        original = copy.deepcopy(item)
        corrected = reviewed_publication_entry(item)
        self.assertEqual(corrected['published_at'].isoformat(), '2017-02-01T20:06:00+00:00')
        self.assertEqual(item, original)
        # A fresh report about a historical election remains eligible.
        fresh = dict(item, id='fresh', url='https://www.tf1info.fr/politique/fresh.html',
                     headline='Présidentielle 2027 : Dupont-Aignan revient sur son programme de 2017')
        self.assertEqual(reviewed_publication_entry(fresh), fresh)

    def test_tf1_cannot_reenter_public_lanes_from_retained_inventory(self):
        from fetch_news_wire import build_wire
        from test_news_wire_relevance import successful_fetch
        inventory = json.loads((ROOT / 'test_fixtures/news/tf1_publication_review.json').read_text(encoding='utf-8'))
        self.assertEqual(len(inventory['items']), 2)
        before = copy.deepcopy(inventory['items'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inventory.json'
            path.write_text(json.dumps(inventory), encoding='utf-8')
            with patch('fetch_news_wire.fetch_news_route', side_effect=lambda url, **kwargs:
                       successful_fetch(b'<rss version="2.0"><channel/></rss>', url)):
                wire, retained = build_wire(ROOT / 'polls.json', 30, 0, path,
                    generated_at=datetime(2026, 11, 2, 3, tzinfo=timezone.utc),
                    candidacy_status_path=ROOT / 'candidate_candidacy_status.json')
        self.assertEqual(retained['items'], before)
        for lane in ('election_news', 'notable_developments', 'relevant_news', 'candidate_watch'):
            self.assertNotIn('c491c4023d07b5c39aee', {row['id'] for row in wire[lane]})
        self.assertIn('8f3f10964f121c62940e', {row['id'] for row in wire['candidate_watch']})

    def test_python_and_browser_fallback_use_identical_complete_periods(self):
        from test_runoff_workspace import run_runoff_script
        payload = {'generated_at': '2026-11-02T02:39:41Z', 'candidate_watch': []}
        result = run_runoff_script(None, 'api.deriveCandidateVisibility(' + json.dumps(payload) + ')')
        expected = build_candidate_visibility([], datetime(2026, 11, 2, 2, tzinfo=timezone.utc))
        for period in ('current_period', 'prior_period'):
            self.assertEqual(result[period]['start_date'], expected[period]['start_date'])
            self.assertEqual(result[period]['end_date'], expected[period]['end_date'])

    def test_retained_visibility_contract_is_readable_but_new_partial_days_fail(self):
        from fetch_news_wire import validate_output, validate_candidate_visibility
        from test_candidate_provider_rosters import historical_publication
        retained = json.loads(historical_publication()['news_wire.json'])
        original = copy.deepcopy(retained)
        validate_output(retained)
        self.assertEqual(retained, original)
        # A same-day end is no longer acceptable for a new publication.
        partial = build_candidate_visibility([], datetime(2026, 11, 3, tzinfo=timezone.utc))
        with self.assertRaisesRegex(RuntimeError, 'periods are invalid'):
            validate_candidate_visibility(partial, [], datetime(2026, 11, 2, tzinfo=timezone.utc))

    def test_active_share_rounding_boundaries(self):
        # Fixed expectations pin the publication policy independently of live data.
        # Half ties go toward positive infinity, including negative changes.
        for numerator, denominator, expected in (
            (18, 480, 0.038),
            (1, 16, 0.063),
            (1, 2000, 0.001),
            (-1, 16, -0.062),
            (-1, 2000, 0.0),
            (37499, 1000000, 0.037),
            (37501, 1000000, 0.038),
            (-62501, 1000000, -0.063),
            (-62499, 1000000, -0.062),
        ):
            with self.subTest(numerator=numerator, denominator=denominator):
                self.assertEqual(
                    _round_visibility_ratio(numerator / denominator), expected)

    def test_published_active_shares_recompute_from_records(self):
        wire = json.loads((ROOT / 'news_wire.json').read_text(encoding='utf-8'))
        signals = json.loads((ROOT / 'candidate_signals.json').read_text(encoding='utf-8'))
        registry = json.loads((ROOT / 'candidate_candidacy_status.json').read_text(encoding='utf-8'))
        active = signals['active_monitoring_field']
        names = {row['candidate_name'] for row in registry['candidates'] if row['candidate_id'] in
                 set(active['main'] + active['secondary'])}
        primary = signals['active_field_visibility']['primary']
        periods = []
        for period_name in ('current_period', 'prior_period'):
            period = primary[period_name]
            records = {row['id']: row for row in wire['candidate_watch']
                       if row['coverage_scope'] in ('election', 'campaign')
                       and period['start_date'] <= row['published_at'][:10] <= period['end_date']
                       and names.intersection(row['candidates'])}
            self.assertEqual(len(records), period['record_count'])
            periods.append(records)
        for row in primary['main'] + primary['secondary']:
            counts = [sum(row['candidate_name'] in record['candidates'] for record in records.values())
                      for records in periods]
            # Recount the source records independently, then apply the same
            # publication rounding to both periods and their rounded-share delta.
            shares = [_round_visibility_ratio(count / len(records)) if records else None
                      for count, records in zip(counts, periods)]
            self.assertEqual(counts, [row['current_record_count'], row['prior_record_count']])
            self.assertEqual(shares, [row['current_share'], row['prior_share']])
            if primary['comparison_quality']['status'] == 'comparable':
                self.assertEqual(row['share_change'], _round_visibility_ratio(shares[0] - shares[1]))


if __name__ == '__main__':
    unittest.main()
