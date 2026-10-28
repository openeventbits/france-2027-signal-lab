// Controlled execution of the real Polling Lab functions; no browser/PDF cache.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = __dirname;
const full = JSON.parse(fs.readFileSync(path.join(root, 'poll_explorer.json'), 'utf8'));
// Preserve actual objects/IDs while keeping these historical studies recent
// in this controlled test as new production waves arrive.
const selected = [full.waves[0],
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
      candidateLatestPollMeta, chartWaves, directoryCounts, directoryPeriod, wavePagePath,
      setData(value) { state.data = validateData(value); },
      setInstitute(value) { state.institute = value; }};
  })();`, context);
  const api = context.api;
  const clone = () => JSON.parse(JSON.stringify(payload));
  api.setData(clone());
  const entries = api.directoryEntries();
  assert.equal(entries.length, payload.waves.length + 2);
  assert.equal(new Set(entries.map(e => e.wave_id || e.source_scenario_id)).size, entries.length);
  const latest = entries.slice(0, 10).filter(e => e.kind === 'reviewed_source_scenario');
  assert.equal(latest.length, 2);
  assert.equal(latest[0].notice_id, '10333');
  assert.equal(latest[1].notice_id, '10319');
  const numericInstitute = JSON.stringify(payload.institutes.find(i => i.name === 'OpinionWay'));
  const opinionway = entries.filter(e => e.pollster === 'OpinionWay');
  assert.equal(api.directoryPeriod(opinionway).end, '2026-10-22');
  assert(opinionway.some(e => e.notice_id === '10333' && e.fieldwork_end === '2026-10-22'));
  const numericalPeriod = api.directoryPeriod(opinionway.filter(e => !e.source_scenario_id));
  assert(numericalPeriod.end < api.directoryPeriod(opinionway).end);
  assert.equal(JSON.stringify(payload.institutes.find(i => i.name === 'OpinionWay')), numericInstitute);
  const lisnard = api.candidateBrowseWaves('david-lisnard').filter(e => e.kind === 'reviewed_source_scenario');
  assert.deepEqual(Array.from(lisnard, e => e.candidates.find(c => c.candidate_id === 'david-lisnard').result.literal), ['6%', '4%']);
  for (const entry of latest) {
    assert.equal(entry.commissioner, 'CNEWS');
    assert.equal(entry.candidates.length, 13);
    assert.equal(api.wavePagePath(entry), entry[lang === 'fr' ? 'page_path_fr' : 'page_path_en']);
    assert.equal(api.candidateWaveScoreMeta(entry, 'david-lisnard'), null);
    assert.equal(api.scoreObservationsForWave(entry, 'david-lisnard').length, 0);
    assert.equal(api.rangeRowsForWave(entry).length, 0);
  }
  assert.equal(latest.flatMap(e => e.candidates).filter(c => c.result.literal === '<1%').length, 3);
  assert(api.directoryCounts(entries).includes(String(waves.length)));
  const numericChart = JSON.stringify(api.chartWaves());
  const numericHeadline = JSON.stringify(api.candidateLatestPollMeta('david-lisnard'));
  const withoutSources = clone();
  withoutSources.source_scenarios = [];
  api.setData(withoutSources);
  assert.equal(JSON.stringify(api.chartWaves()), numericChart);
  assert.equal(JSON.stringify(api.candidateLatestPollMeta('david-lisnard')), numericHeadline);
  api.setData(clone());
  api.setInstitute('OpinionWay');
  assert(api.chartWaves().every(e => e.pollster === 'OpinionWay' && !e.source_scenario_id));
  for (const mutate of [
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
