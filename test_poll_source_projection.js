// Controlled execution of the real Polling Lab functions; no browser/PDF cache.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = __dirname;
const full = JSON.parse(fs.readFileSync(path.join(root, 'poll_explorer.json'), 'utf8'));
// Preserve actual objects/IDs while keeping these historical studies recent
// in this controlled test as new production waves arrive.
const selected = [full.waves[0], full.waves.find(w => w.wave_id === 'wave-5cfde20f50cfb247'),
  full.waves.find(w => w.pollster === 'OpinionWay' && w.fieldwork_end === '2026-10-14'),
  full.waves.find(w => w.scenarios.some(s => s.candidates.some(c => c.candidate_id === 'david-lisnard')))];
const waves = [...new Map(selected.filter(Boolean).map(w => [w.wave_id, w])).values()];
const payload = {...full, waves, metrics: {...full.metrics, wave_count:waves.length}};
const script = fs.readFileSync(path.join(root, 'assets/polling-lab.js'), 'utf8');
const startup = script.indexOf('  if (document.readyState === "loading")');
assert(startup > 0);
for (const lang of ['fr', 'en']) {
  const context = vm.createContext({document: {documentElement: {lang}}, Intl, console});
  vm.runInContext(fs.readFileSync(path.join(root, 'assets/poll-scope.js'), 'utf8'), context);
  vm.runInContext(script.slice(0, startup) + `
    globalThis.api = {validateData, directoryEntries, candidateBrowseWaves,
      candidateWaveScoreMeta, scoreObservationsForWave, rangeRowsForWave,
      candidateLatestPollMeta, chartWaves, directoryCounts, directoryPeriod, wavePagePath, sourceStatus, directoryPollster,
      setData(value) { state.data = validateData(value); },
      setInstitute(value) { state.institute = value; }};
  })();`, context);
  const api = context.api;
  const clone = () => JSON.parse(JSON.stringify(payload));
  api.setData(clone());
  const entries = api.directoryEntries();
  assert.equal(entries.length, payload.waves.length + 4);
  assert.equal(new Set(entries.map(e => e.wave_id || e.source_scenario_id)).size, entries.length);
  const latest = entries.slice(0, 10).filter(e => e.kind === 'reviewed_source_scenario');
  assert.equal(latest.length, 4);
  assert.equal(latest[0].notice_id, '10333');
  assert.equal(latest[1].notice_id, '10319');
  assert.equal(latest[2].notice_id, '10260');
  assert.equal(latest[3].notice_id, '10264');
  const bonnal = latest[3];
  assert.equal(bonnal.publication_date, null);
  assert.equal(bonnal.fieldwork_start, '2026-09-02');
  assert.equal(bonnal.fieldwork_end, '2026-09-04');
  assert.equal(bonnal.commissioner, 'Sébastien Bonnal');
  assert.equal(bonnal.candidates.find(c => c.candidate_id === 'sebastien-bonnal').result.literal, '<1%');
  assert(!payload.candidates.some(c => c.candidate_id === 'sebastien-bonnal'));
  assert.equal(api.candidateBrowseWaves('sebastien-bonnal').length, 1);
  assert.equal(api.candidateLatestPollMeta('sebastien-bonnal'), null);
  assert.equal(api.scoreObservationsForWave(bonnal, 'sebastien-bonnal').length, 0);
  assert.equal(api.rangeRowsForWave(bonnal).length, 0);
  const h3 = latest.find(e => e.notice_id === '10260');
  const h12 = entries.find(e => e.wave_id === 'wave-5cfde20f50cfb247');
  assert.equal(h12.scenario_count, 2);
  assert.deepEqual(new Set(h12.scenarios.map(s => s.event_id)), new Set([
    '34b67c973777cf14f9c19068b4642d119367e3312053f442ba16e9612c051cac',
    '547d14cf13fb2f407e743b91f6347dad9c0a3db48e750b380bdfc27b8fede2cd'
  ]));
  assert.equal(h3.survey_id, 'commission:10260');
  assert.equal(h3.publication_date, null);
  assert.equal(h3.source.pdf_page, 14);
  assert.equal(h3.commissioner, 'CNews');
  assert(api.sourceStatus(h3).includes('H3'));
  assert(api.directoryPollster(h3).includes('CNews · H3'));
  const numericBoundCandidates = ['nathalie-arthaud', 'karim-bouamrane'].map(id => {
    assert.equal(h3.candidates.find(c => c.candidate_id === id).result.literal, '<1%');
    assert(api.candidateBrowseWaves(id).some(w => w === h3));
    assert(api.candidateBrowseWaves(id).some(w => w === h12));
    assert.equal(api.scoreObservationsForWave(h3, id).length, 0);
    assert.equal(api.candidateWaveScoreMeta(h3, id), null);
    return [id, JSON.stringify(api.candidateLatestPollMeta(id)), JSON.stringify(api.scoreObservationsForWave(h12, id))];
  });
  assert.equal(api.rangeRowsForWave(h3).length, 0);
  const numericInstitute = JSON.stringify(payload.institutes.find(i => i.name === 'OpinionWay'));
  const opinionway = entries.filter(e => e.pollster === 'OpinionWay');
  assert.equal(api.directoryPeriod(opinionway).end, '2026-10-22');
  assert(opinionway.some(e => e.notice_id === '10333' && e.fieldwork_end === '2026-10-22'));
  const numericalPeriod = api.directoryPeriod(opinionway.filter(e => !e.source_scenario_id));
  assert(numericalPeriod.end < api.directoryPeriod(opinionway).end);
  assert.equal(JSON.stringify(payload.institutes.find(i => i.name === 'OpinionWay')), numericInstitute);
  const lisnard = api.candidateBrowseWaves('david-lisnard').filter(e => e.kind === 'reviewed_source_scenario');
  assert.deepEqual(Array.from(lisnard, e => e.candidates.find(c => c.candidate_id === 'david-lisnard').result.literal), ['6%', '4%', '2%']);
  for (const entry of latest) {
    assert.equal(entry.commissioner, entry.notice_id === '10264' ? 'Sébastien Bonnal' : entry.notice_id === '10260' ? 'CNews' : 'CNEWS');
    assert.equal(entry.candidates.length, entry.notice_id === '10264' ? 11 : 13);
    assert.equal(api.wavePagePath(entry), entry[lang === 'fr' ? 'page_path_fr' : 'page_path_en']);
    assert.equal(api.candidateWaveScoreMeta(entry, 'david-lisnard'), null);
    assert.equal(api.scoreObservationsForWave(entry, 'david-lisnard').length, 0);
    assert.equal(api.rangeRowsForWave(entry).length, 0);
  }
  assert.equal(latest.flatMap(e => e.candidates).filter(c => c.result.literal === '<1%').length, 6);
  assert(api.directoryCounts(entries).includes(String(waves.length)));
  const numericChart = JSON.stringify(api.chartWaves());
  const numericHeadline = JSON.stringify(api.candidateLatestPollMeta('david-lisnard'));
  const withoutSources = clone();
  withoutSources.source_scenarios = [];
  api.setData(withoutSources);
  assert.equal(JSON.stringify(api.chartWaves()), numericChart);
  assert.equal(JSON.stringify(api.candidateLatestPollMeta('david-lisnard')), numericHeadline);
  for (const [id, headline, observations] of numericBoundCandidates) {
    assert.equal(JSON.stringify(api.candidateLatestPollMeta(id)), headline);
    assert.equal(JSON.stringify(api.scoreObservationsForWave(h12, id)), observations);
  }
  api.setData(clone());
  api.setInstitute('OpinionWay');
  assert(api.chartWaves().every(e => e.pollster === 'OpinionWay' && !e.source_scenario_id));
  const h3Entry = p => p.source_scenarios.find(e => e.notice_id === '10260');
  for (const mutate of [
    ...['nathalie-arthaud','karim-bouamrane'].flatMap(id => [0,0.5,1].map(value => p => {
      h3Entry(p).candidates.find(c => c.candidate_id === id).result = {kind:'exact',percent:value,literal:String(value)+'%'};
    })),
    p => h3Entry(p).candidates[0].candidate_id = 'someone-else',
    p => h3Entry(p).candidates[0].candidate_name = 'Nathalie Arthaud (changed)',
    p => h3Entry(p).candidate_ids[0] = 'someone-else',
    p => h3Entry(p).candidates[1].result = {kind:'exact',percent:18,literal:'18%'},
    p => h3Entry(p).source.pdf_sha256 = '0'.repeat(64),
    p => h3Entry(p).source.pdf_url = 'https://example.com/other.pdf',
    p => h3Entry(p).source.pdf_page = 12,
    p => h3Entry(p).publication_date = '2026-09-11',
    p => h3Entry(p).fieldwork_end = '2026-09-11',
    p => h3Entry(p).respondent_bases.expressed_certain_voters = 690,
    p => h3Entry(p).commissioner = 'CNEWS',
    p => h3Entry(p).survey_id = 'commission:10319',
    p => h3Entry(p).analysis_eligible = true,
    p => h3Entry(p).event_id = 'fictional',
    p => h3Entry(p).wave_id = 'fictional',
    p => h3Entry(p).scenarios = [{candidates:[]}],
    p => h3Entry(p).page_path_fr = '/unauthorized/',
    p => h3Entry(p).page_path_en = '/en/unauthorized/',
    p => p.source_scenarios.push(h3Entry(p)),
    p => p.waves.push(h3Entry(p)),
    ...[0, 0.5, 1].map(value => p => {
      const entry = p.source_scenarios.find(e => e.notice_id === '10264');
      entry.candidates.find(c => c.candidate_id === 'sebastien-bonnal').result =
        {kind: 'exact', percent: value, literal: String(value) + '%'};
    }),
    p => p.source_scenarios.find(e => e.notice_id === '10264').commissioner = 'Facebook',
    p => p.source_scenarios.find(e => e.notice_id === '10264').publication_date = '2026-09-15',
    p => p.source_scenarios.find(e => e.notice_id === '10264').record_sha256 = '0'.repeat(64),
    p => p.source_scenarios.find(e => e.notice_id === '10264').page_path_fr = '/preview/evidence/10264/fr/',
    p => p.source_scenarios.push(p.source_scenarios[0]),
    p => p.source_scenarios[0].commissioner = 'Les Échos',
    p => p.source_scenarios[0].analysis_eligible = true,
    p => p.source_scenarios[0].event_id = 'fictional',
    p => p.source_scenarios[0].candidates[0].score = 1,
    p => p.source_scenarios[0].candidates.pop(),
    p => p.source_scenarios[0].candidates[0].result.percent = '1',
    p => { const c = p.source_scenarios[0].candidates.find(c => c.result.kind === 'strict_upper_bound'); c.result.percent = 0.5; },
    p => p.waves.push(p.source_scenarios[0]),
    p => p.waves[0].scenarios[0].candidates[0].result = {kind:'strict_upper_bound', upper_percent:1, literal:'<1%'}
  ]) {
    const bad = clone(); mutate(bad);
    assert.throws(() => api.validateData(bad));
  }
}
console.log('PASS: FR/EN browsing, typed literals, duplicate rejection and numerical analysis isolation');
