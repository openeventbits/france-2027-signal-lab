// Execute the shipped FR/EN code. These checks do not reproduce the filters.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const read = name => fs.readFileSync(path.join(__dirname, name), 'utf8');
const polls = JSON.parse(read('polls.json'));
const payload = JSON.parse(read('poll_explorer.json'));
const registry = JSON.parse(read('poll_election_scope.json'));
const excluded = new Set(Object.keys(registry.events));
const mixedId = '7620aec7d2dad43cf848da79b84195f0bd5625aa77ce3eb849dd2d8c36ce4780';
const mixed = payload.waves.find(w => w.scenarios.some(s => s.event_id === mixedId));
const lab = read('assets/polling-lab.js');
const startup = lab.indexOf('  if (document.readyState === "loading")');
assert(startup > 0);
for (const lang of ['fr', 'en']) {
  const hub = read(lang === 'fr' ? 'sondages/index.html' : 'en/sondages/index.html');
  assert(hub.indexOf('poll-scope.js') < hub.indexOf('polling-lab.js'), 'Scope must load before the Polling Lab');
  const context = vm.createContext({document: {documentElement: {lang}}, Intl, console});
  vm.runInContext(read('assets/poll-scope.js'), context);
  const scope = context.FR27PollScope;
  const rawBefore = JSON.stringify(polls);
  scope.verifyCollection(polls);
  assert.equal(polls.filter(e => scope.eligible(e)).length, polls.length - 6);
  for (const event of polls.filter(e => excluded.has(e.event_id))) {
    assert.equal(scope.scope(event), 'retrospective_2022_revote');
    const synthetic = structuredClone(event);
    synthetic.event_id = 'f'.repeat(64); // Same date, Macron, lineup, URL, scenario key.
    assert.equal(scope.scope(synthetic), 'not_yet_reviewed');
    assert(scope.eligible(synthetic));
    const changed = structuredClone(event);
    changed.candidates[0].score += 1;
    assert.throws(() => scope.scope(changed), /changed/);
  }
  assert.throws(() => scope.verifyCollection(polls.filter(e => !excluded.has(e.event_id))), /Missing/);
  assert.throws(() => scope.verifyCollection([...polls, polls[0]]), /Duplicate/);
  assert.equal(JSON.stringify(polls), rawBefore);
  vm.runInContext(lab.slice(0, startup) + `
    globalThis.api = {validateData, defaultWaves, defaultScenarios, chartWaves,
      candidateLatestPollMeta, scoreObservationsForWave, sharedComparableSeries,
      candidateWaveScoreMeta, rangeRowsForWave, scenarioPageHref, directoryEntries,
      waveScopeLabel, directoryCounts, candidateBrowseWaves,
      setData(data) { state.data = validateData(data); state.period = "all"; },
      select(ids) { state.selectedCandidateIds = ids; }};
  })();`, context);
  const api = context.api;
  api.setData(structuredClone(payload));
  api.select(['marine-le-pen', 'jean-luc-melenchon']);
  assert.equal(api.directoryEntries().length, payload.waves.length + payload.source_scenarios.length);
  assert.equal(api.defaultWaves().length, payload.waves.length - 5);
  assert.equal(api.defaultScenarios(mixed).length, 5);
  assert.equal(api.scoreObservationsForWave(mixed, 'marine-le-pen').length, 5);
  assert.equal(api.candidateWaveScoreMeta(mixed, 'marine-le-pen').scenarioCount, 5);
  assert.equal(api.candidateWaveScoreMeta(mixed, 'emmanuel-macron'), null);
  assert(!api.rangeRowsForWave(mixed).some(row => row.candidateId === 'emmanuel-macron'));
  assert.equal(api.rangeRowsForWave(mixed).find(row => row.candidateId === 'marine-le-pen').scenarioCount, 5);
  const retrospective = mixed.scenarios.find(s => s.event_id === mixedId);
  assert.equal(api.scenarioPageHref(mixed, retrospective), mixed[`page_path_${lang}`] + '#scenario-4');
  assert(api.waveScopeLabel(mixed).includes('2022'));
  assert.equal(api.candidateLatestPollMeta('emmanuel-macron'), null);
  assert.equal(api.candidateBrowseWaves('emmanuel-macron').length, 0);
  assert(api.candidateBrowseWaves('marine-le-pen').every(w => w.source_scenario_id || api.defaultScenarios(w).length > 0));
  const chart = api.chartWaves();
  for (const wave of chart) {
    assert(api.defaultScenarios(wave).length > 0);
    assert(api.scoreObservationsForWave(wave, 'marine-le-pen').every(o => !excluded.has(o.scenario.event_id)));
  }
  for (const series of api.sharedComparableSeries(payload.waves)) {
    assert(series.occurrences.every(o => !excluded.has(o.scenario.event_id)));
  }
  for (const wave of payload.waves.filter(w => w.scenarios.every(s => excluded.has(s.event_id)))) {
    assert.equal(api.scoreObservationsForWave(wave, 'marine-le-pen').length, 0);
    assert.equal(api.rangeRowsForWave(wave).length, 0);
    assert.equal(api.candidateWaveScoreMeta(wave, 'marine-le-pen'), null);
    assert(api.directoryEntries().some(w => w.wave_id === wave.wave_id));
  }
  for (const mutate of [
    p => p.waves.find(w => w.wave_id === mixed.wave_id).scenarios.find(s => s.event_id === mixedId).election_scope = 'not_yet_reviewed',
    p => p.waves[0].scenarios[0].election_scope = 'retrospective_2022_revote',
    p => delete p.waves[0].scenarios[0].election_scope,
    p => delete p.default_2027,
  ]) {
    const bad = structuredClone(payload); mutate(bad);
    assert.throws(() => api.validateData(bad));
  }
  const shell = read(lang === 'fr' ? 'index.html' : 'en/index.html');
  const begin = shell.indexOf('    function candidateScore(');
  const end = shell.indexOf('    function formatComparableChange(');
  assert(begin > 0 && end > begin);
  vm.runInContext(shell.slice(begin, end) + `
    globalThis.home = {isValidFirstRoundPollEvent, deriveComparableChange, deriveRacePreviousPollDifference};
  `, context);
  const rankingStart = shell.indexOf('    function raceComparableCandidateCount(');
  const rankingEnd = shell.indexOf('    function selectRacePoll(');
  assert(rankingStart > 0 && rankingEnd > rankingStart);
  vm.runInContext('const raceGlanceState = {selectedHypothesisByPoll: {}};\n'
    + shell.slice(rankingStart, rankingEnd) + '\nglobalThis.rank = rankRacePollPackages;', context);
  const rawPackages = payload.waves.map(wave => ({...wave, key: wave.wave_id,
    events: wave.scenarios.map(scenario => polls.find(event => event.event_id === scenario.event_id))}));
  const beforeRanking = JSON.stringify(rawPackages);
  const ranked = context.rank(rawPackages, polls);
  assert.equal(ranked.length, payload.waves.length - 5);
  assert(ranked.every(pkg => pkg.events.every(event => !excluded.has(event.event_id))));
  assert.equal(ranked.find(pkg => pkg.wave_id === mixed.wave_id).events.length, 5);
  assert.equal(JSON.stringify(rawPackages), beforeRanking);
  assert.equal(polls.filter(e => context.home.isValidFirstRoundPollEvent(e)).length, polls.length - 6);
  assert.equal(polls.filter(context.home.isValidFirstRoundPollEvent).length, polls.length - 6);
  assert.equal(polls.filter(e => context.home.isValidFirstRoundPollEvent(e, {includeHistorical: true})).length, polls.length);
  const historical = polls.filter(e => excluded.has(e.event_id));
  assert.equal(context.home.deriveComparableChange(historical, 'Marine Le Pen', '2023-10-20').retained.length, 0);
  assert.equal(context.home.deriveRacePreviousPollDifference(historical, 'Marine Le Pen', historical[0]).classification, 'NO_PRIOR');
  // A new ID with the same ballot and Macron is eligible; retrospective priors cannot enter its difference.
  const synthetic = structuredClone(historical[0]); synthetic.event_id = 'e'.repeat(64);
  assert(context.home.isValidFirstRoundPollEvent(synthetic));
  assert.equal(context.home.deriveRacePreviousPollDifference(historical, 'Marine Le Pen', synthetic).classification, 'NO_PRIOR');
}
console.log('PASS: FR/EN default scope, mixed-wave ranges, histories, archive routes, negative controls and raw preservation');
