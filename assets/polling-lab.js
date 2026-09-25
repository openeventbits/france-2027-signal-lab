(() => {
  "use strict";

  const PAGE_LANG = document.documentElement.lang.toLowerCase().startsWith("en") ? "en" : "fr";
  const LOCALE_TAG = PAGE_LANG === "en" ? "en-GB" : "fr-FR";
  const ROOT_PREFIX = PAGE_LANG === "en" ? "../.." : "..";

  const DATA_URL = `${ROOT_PREFIX}/poll_explorer.json`;
  const CANDIDATE_SIGNALS_URL = `${ROOT_PREFIX}/candidate_signals.json`;

  const UI_TEXT = Object.freeze({
    fr: Object.freeze({
      noPublishedScore: "AUCUN SCORE PUBLIÉ",
      maximumFive: "MAXIMUM 5",
      addCandidate: "+ AJOUTER UN CANDIDAT",
      noObservationSelected: "AUCUNE OBSERVATION SÉLECTIONNÉE",
      observationInspectorHint: "La sélection d’une observation affichera l’institut, le terrain, le scénario, les résultats candidats, l’échantillon et la source publiée.",
      repeatedExactBallot: "BULLETIN EXACT RÉPÉTÉ",
      samePollsterSameScenario: "Même institut + même scénario",
      scenario: "SCÉNARIO",
      firstRound: "PREMIER TOUR",
      publishedResults: "RÉSULTATS PUBLIÉS",
      viewPublishedSource: "VOIR LA SOURCE PUBLIÉE ↗",
      sourceUnavailable: "SOURCE INDISPONIBLE",
      identicalBallotComparison: "COMPARAISON À BULLETIN IDENTIQUE",
      identicalBallotExplanation: "Chaque tige relie les candidats sélectionnés testés dans la même vague. L’axe horizontal conserve le temps réel.",
      noWaveAvailable: "Aucune vague disponible.",
      uniqueValue: "VALEUR UNIQUE",
      source: "SOURCE ↗",
      openPoll: "OUVRIR →",
      pollPage: "SONDAGE",
      pageUnavailable: "PAGE INDISPONIBLE",
      sources: "SOURCES",
      selectInstitute: "Sélectionnez un institut pour ouvrir son répertoire de vagues.",
      alreadySelected: "DÉJÀ SÉLECTIONNÉ",
      addToComparison: "+ AJOUTER À LA COMPARAISON",
      noObservation: "AUCUNE OBSERVATION",
      selectCandidate: "Sélectionnez un candidat pour consulter ses vagues et ses scores publiés.",
      dataUnavailable: "Données indisponibles.",
      loadFailure: "Impossible de charger le Polling Lab.",
      wave: "VAGUE",
      waves: "VAGUES",
      scenarioLower: "scénario",
      scenariosLower: "scénarios",
      observation: "OBSERVATION",
      observations: "OBSERVATIONS",
      shared: "PARTAGÉE",
      sharedPlural: "PARTAGÉES",
      exactBallot: "BULLETIN EXACT RÉPÉTÉ",
      exactBallots: "BULLETINS EXACTS RÉPÉTÉS",
      pollsterLower: "institut",
      fieldworkLower: "terrain",
      respondents: "répondants",
      fieldwork: "TERRAIN",
      pollster: "INSTITUT",
      scenarios: "SCÉNARIOS",
      sample: "ÉCHANTILLON",
      candidates: "CANDIDATS",
      sourceLabel: "SOURCE",
      minimumLower: "minimum",
      maximumLower: "maximum",
      rangeLower: "étendue",
      testedInLower: "testé dans",
      waveLower: "vague",
      wavesLower: "vagues",
      candidate: "CANDIDAT",
      pollsters: "INSTITUTS",
      collapseDirectory: "RÉDUIRE LE RÉPERTOIRE",
      showRemainingPrefix: "AFFICHER LES",
      remainingWaves: "VAGUES RESTANTES",
      removeCandidate: "Retirer",
      publishedLabel: "LIBELLÉ PUBLIÉ",
      selectedCandidateLegend: "CANDIDAT SÉLECTIONNÉ",
      sameBallotSameWaveLegend: "MÊME BULLETIN · MÊME VAGUE",
      selectedExactRepetitionLegend: "RÉPÉTITION EXACTE SÉLECTIONNÉE",
      publishedObservationLegend: "OBSERVATION PUBLIÉE",
      withinWaveRangeLegend: "ÉTENDUE DANS UNE MÊME VAGUE",
      comparableSeriesLegend: "SÉRIE COMPARABLE",
      publishedObservationsAria: "Observations de sondage publiées",
      comparableBallotsAria: "Comparaison des candidats dans des bulletins exacts répétés sur un axe temporel réel",
      fieldworkAt: "terrain au",
      selectUpToFive: "SÉLECTIONNEZ JUSQU’À 5 CANDIDATS",
      publishedObservationsAppearHere: "Les observations publiées apparaîtront ici.",
      selectionRequired: "SÉLECTION REQUISE",
      noData: "AUCUNE DONNÉE",
      noDataToDisplay: "AUCUNE DONNÉE À AFFICHER",
      noComparableForFilters: "Aucun bulletin exact répété ne contient tous les candidats sélectionnés avec ces filtres.",
      noObservationForFilters: "Aucune observation publiée pour cette sélection et ces filtres.",
      invalidDataObject: "Le fichier de données n’est pas un objet valide.",
      unsupportedDataVersion: "Version de données Polling Lab non prise en charge.",
      missingMetrics: "Métriques Polling Lab absentes.",
      incompleteDirectories: "Répertoires Polling Lab incomplets.",
      incompleteMetrics: "Métriques Polling Lab incomplètes.",
      malformedWave: "Une vague de sondage est mal formée.",
      duplicateWaveId: "Identifiant de vague dupliqué.",
      malformedScenario: "Un scénario de sondage est mal formé.",
      duplicateScenarioId: "Identifiant de scénario dupliqué.",
      activeFieldUnavailable: "Univers de candidats actif indisponible.",
      activeFieldMalformed: "Univers de candidats actif mal formé.",
      invalidActiveCandidateIds: "Identifiants de candidats actifs invalides.",
      duplicateActiveCandidateId: "Identifiant de candidat actif dupliqué.",
      pollHttpError: "Réponse Polling Lab HTTP",
      candidateUniverseHttpError: "Réponse univers candidats HTTP"
    }),
    en: Object.freeze({
      noPublishedScore: "NO PUBLISHED SCORE",
      maximumFive: "MAXIMUM 5",
      addCandidate: "+ ADD CANDIDATE",
      noObservationSelected: "NO OBSERVATION SELECTED",
      observationInspectorHint: "Selecting an observation will show the pollster, fieldwork, scenario, candidate results, sample and published source.",
      repeatedExactBallot: "REPEATED EXACT BALLOT",
      samePollsterSameScenario: "Same pollster + same scenario",
      scenario: "SCENARIO",
      firstRound: "FIRST ROUND",
      publishedResults: "PUBLISHED RESULTS",
      viewPublishedSource: "VIEW PUBLISHED SOURCE ↗",
      sourceUnavailable: "SOURCE UNAVAILABLE",
      identicalBallotComparison: "IDENTICAL BALLOT COMPARISON",
      identicalBallotExplanation: "Each stem connects the selected candidates tested in the same wave. The horizontal axis preserves real calendar time.",
      noWaveAvailable: "No wave available.",
      uniqueValue: "SINGLE VALUE",
      source: "SOURCE ↗",
      openPoll: "OPEN →",
      pollPage: "POLL",
      pageUnavailable: "PAGE UNAVAILABLE",
      sources: "SOURCES",
      selectInstitute: "Select a pollster to open its wave directory.",
      alreadySelected: "ALREADY SELECTED",
      addToComparison: "+ ADD TO COMPARISON",
      noObservation: "NO OBSERVATION",
      selectCandidate: "Select a candidate to view their waves and published scores.",
      dataUnavailable: "Data unavailable.",
      loadFailure: "Unable to load Polling Lab.",
      wave: "WAVE",
      waves: "WAVES",
      scenarioLower: "scenario",
      scenariosLower: "scenarios",
      observation: "OBSERVATION",
      observations: "OBSERVATIONS",
      shared: "SHARED",
      sharedPlural: "SHARED",
      exactBallot: "REPEATED EXACT BALLOT",
      exactBallots: "REPEATED EXACT BALLOTS",
      pollsterLower: "pollster",
      fieldworkLower: "fieldwork",
      respondents: "respondents",
      fieldwork: "FIELDWORK",
      pollster: "POLLSTER",
      scenarios: "SCENARIOS",
      sample: "SAMPLE",
      candidates: "CANDIDATES",
      sourceLabel: "SOURCE",
      minimumLower: "minimum",
      maximumLower: "maximum",
      rangeLower: "range",
      testedInLower: "tested in",
      waveLower: "wave",
      wavesLower: "waves",
      candidate: "CANDIDATE",
      pollsters: "POLLSTERS",
      collapseDirectory: "COLLAPSE DIRECTORY",
      showRemainingPrefix: "SHOW",
      remainingWaves: "REMAINING WAVES",
      removeCandidate: "Remove",
      publishedLabel: "PUBLISHED LABEL",
      selectedCandidateLegend: "SELECTED CANDIDATE",
      sameBallotSameWaveLegend: "SAME BALLOT · SAME WAVE",
      selectedExactRepetitionLegend: "SELECTED EXACT REPETITION",
      publishedObservationLegend: "PUBLISHED OBSERVATION",
      withinWaveRangeLegend: "WITHIN-WAVE RANGE",
      comparableSeriesLegend: "COMPARABLE SERIES",
      publishedObservationsAria: "Published poll observations",
      comparableBallotsAria: "Candidate comparison across repeated exact ballots on a real calendar timeline",
      fieldworkAt: "fieldwork ended",
      selectUpToFive: "SELECT UP TO 5 CANDIDATES",
      publishedObservationsAppearHere: "Published observations will appear here.",
      selectionRequired: "SELECTION REQUIRED",
      noData: "NO DATA",
      noDataToDisplay: "NO DATA TO DISPLAY",
      noComparableForFilters: "No repeated exact ballot contains all selected candidates under these filters.",
      noObservationForFilters: "No published observation for this selection and these filters.",
      invalidDataObject: "The data file is not a valid object.",
      unsupportedDataVersion: "Unsupported Polling Lab data version.",
      missingMetrics: "Polling Lab metrics are missing.",
      incompleteDirectories: "Polling Lab directories are incomplete.",
      incompleteMetrics: "Polling Lab metrics are incomplete.",
      malformedWave: "A poll wave is malformed.",
      duplicateWaveId: "Duplicate wave identifier.",
      malformedScenario: "A poll scenario is malformed.",
      duplicateScenarioId: "Duplicate scenario identifier.",
      activeFieldUnavailable: "Active candidate field is unavailable.",
      activeFieldMalformed: "Active candidate field is malformed.",
      invalidActiveCandidateIds: "Active candidate identifiers are invalid.",
      duplicateActiveCandidateId: "Duplicate active candidate identifier.",
      pollHttpError: "Polling Lab HTTP response",
      candidateUniverseHttpError: "Candidate universe HTTP response"
    })
  });

  function uiText(key) {
    return UI_TEXT[PAGE_LANG][key];
  }

  function uiPlural(count, singularKey, pluralKey) {
    return uiText(count === 1 ? singularKey : pluralKey);
  }

  const MAX_SELECTED_CANDIDATES = 5;
  const LATEST_WAVE_LIMIT = 10;
  const SLOT_COLORS = ["#35d8ff", "#8b79ff", "#ffbd58", "#48d8ad", "#ef8298"];
  const SVG_NS = "http://www.w3.org/2000/svg";
  const CHART = { left: 58, right: 24, top: 26, bottom: 48 };

  const state = {
    data: null,
    selectedCandidateIds: [],
    period: "all",
    mode: "observations",
    institute: "",
    rangeWaveId: null,
    activeCandidateIds: new Set(),
    pickerCandidates: [],
    latestPollMetaByCandidate: new Map(),
    selectedComparableSeriesKey: null,
    selectedObservationEventId: null,
    selectedObservationCandidateId: null,
    browseMode: "all",
    browseWaveLimit: 15,
    browseInstitute: "",
    browseCandidateId: "",
  };

  const nodes = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function validateData(data) {
    if (!isObject(data)) throw new Error(uiText("invalidDataObject"));
    if (data.schema_version !== "1.0") throw new Error(uiText("unsupportedDataVersion"));
    if (!isObject(data.metrics)) throw new Error(uiText("missingMetrics"));
    if (!Array.isArray(data.candidates) || !Array.isArray(data.institutes) || !Array.isArray(data.waves)) {
      throw new Error(uiText("incompleteDirectories"));
    }

    const metricKeys = ["wave_count", "scenario_count", "candidate_count", "institute_count", "period_start", "period_end"];
    if (!metricKeys.every((key) => Object.hasOwn(data.metrics, key))) {
      throw new Error(uiText("incompleteMetrics"));
    }

    const waveIds = new Set();
    const eventIds = new Set();
    for (const wave of data.waves) {
      if (
        !isObject(wave)
        || typeof wave.wave_id !== "string"
        || typeof wave.page_path_fr !== "string"
        || typeof wave.page_path_en !== "string"
        || !wave.page_path_fr.startsWith("/sondages/")
        || !wave.page_path_en.startsWith("/en/sondages/")
        || !Array.isArray(wave.scenarios)
      ) {
        throw new Error(uiText("malformedWave"));
      }
      if (waveIds.has(wave.wave_id)) throw new Error(uiText("duplicateWaveId"));
      waveIds.add(wave.wave_id);
      for (const scenario of wave.scenarios) {
        if (!isObject(scenario) || typeof scenario.event_id !== "string" || !Array.isArray(scenario.candidates)) {
          throw new Error(uiText("malformedScenario"));
        }
        if (eventIds.has(scenario.event_id)) throw new Error(uiText("duplicateScenarioId"));
        eventIds.add(scenario.event_id);
      }
    }
    return data;
  }

  function formatDate(iso, options = {}) {
    if (!iso) return "—";
    const date = new Date(`${iso}T00:00:00Z`);
    if (Number.isNaN(date.getTime())) return iso;
    return new Intl.DateTimeFormat(LOCALE_TAG, {
      day: "numeric",
      month: options.short ? "short" : "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }

  function formatScore(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return `${new Intl.NumberFormat(LOCALE_TAG, { maximumFractionDigits: 1 }).format(value)} %`;
  }

  function formatPoints(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return `${new Intl.NumberFormat(LOCALE_TAG, { maximumFractionDigits: 1 }).format(value)} pt${Math.abs(value) === 1 ? "" : "s"}`;
  }

  function formatInteger(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return new Intl.NumberFormat(LOCALE_TAG).format(value);
  }

  function wavePagePath(wave) {
    const key = PAGE_LANG === "en" ? "page_path_en" : "page_path_fr";
    const value = wave?.[key];

    return typeof value === "string" && value.startsWith("/")
      ? value
      : "";
  }

  function scenarioPageHref(wave, scenario) {
    const base = wavePagePath(wave);
    if (!base) return "";

    const index = Array.isArray(wave?.scenarios)
      ? wave.scenarios.findIndex(
          (item) => item?.event_id === scenario?.event_id
        )
      : -1;

    return index >= 0
      ? `${base}#scenario-${index + 1}`
      : base;
  }

  function createWavePageLink(
    wave,
    text,
    className = "polling-wave-context-link"
  ) {
    const link = document.createElement("a");
    const href = wavePagePath(wave);

    link.className = className;
    link.textContent = text;

    if (href) {
      link.href = href;
    } else {
      link.removeAttribute("href");
      link.setAttribute("aria-disabled", "true");
    }

    return link;
  }

  function candidateById(candidateId) {
    return state.data?.candidates.find((candidate) => candidate.candidate_id === candidateId) || null;
  }

  function validateCandidateSignals(data) {
    if (!isObject(data) || !isObject(data.active_monitoring_field)) {
      throw new Error(uiText("activeFieldUnavailable"));
    }
    const { main, secondary } = data.active_monitoring_field;
    if (!Array.isArray(main) || !Array.isArray(secondary)) {
      throw new Error(uiText("activeFieldMalformed"));
    }
    const candidateIds = [...main, ...secondary];
    if (!candidateIds.every((value) => typeof value === "string" && value.trim())) {
      throw new Error(uiText("invalidActiveCandidateIds"));
    }
    const unique = new Set(candidateIds);
    if (unique.size !== candidateIds.length) {
      throw new Error(uiText("duplicateActiveCandidateId"));
    }
    return unique;
  }

  function candidateLatestPollMeta(candidateId) {
    for (const wave of state.data.waves) {
      const scores = [];
      for (const scenario of wave.scenarios) {
        const candidate = scenario.candidates.find(
          (item) =>
            item.identity_type === "person" &&
            item.candidate_id === candidateId &&
            typeof item.score === "number" &&
            Number.isFinite(item.score)
        );
        if (candidate) scores.push(candidate.score);
      }
      if (scores.length === 0) continue;

      const minimum = Math.min(...scores);
      const maximum = Math.max(...scores);
      return {
        fieldworkEnd: wave.fieldwork_end,
        pollster: wave.pollster,
        minimum,
        maximum,
        sortScore: maximum,
      };
    }
    return null;
  }

  function buildPickerCandidates() {
    state.latestPollMetaByCandidate = new Map();
    const candidates = state.data.candidates.filter((candidate) =>
      state.activeCandidateIds.has(candidate.candidate_id)
    );

    for (const candidate of candidates) {
      state.latestPollMetaByCandidate.set(
        candidate.candidate_id,
        candidateLatestPollMeta(candidate.candidate_id)
      );
    }

    return candidates.sort((left, right) => {
      const leftMeta = state.latestPollMetaByCandidate.get(left.candidate_id);
      const rightMeta = state.latestPollMetaByCandidate.get(right.candidate_id);
      const leftScore = leftMeta?.sortScore;
      const rightScore = rightMeta?.sortScore;
      const leftHasScore = typeof leftScore === "number" && Number.isFinite(leftScore);
      const rightHasScore = typeof rightScore === "number" && Number.isFinite(rightScore);
      if (leftHasScore && rightHasScore && leftScore !== rightScore) return rightScore - leftScore;
      if (leftHasScore !== rightHasScore) return leftHasScore ? -1 : 1;
      if (leftMeta?.fieldworkEnd !== rightMeta?.fieldworkEnd) {
        return String(rightMeta?.fieldworkEnd || "").localeCompare(String(leftMeta?.fieldworkEnd || ""));
      }
      return left.candidate_name.localeCompare(right.candidate_name, PAGE_LANG, { sensitivity: "base" });
    });
  }

  function pickerMetaText(candidateId) {
    const meta = state.latestPollMetaByCandidate.get(candidateId);
    if (!meta) return uiText("noPublishedScore");
    const date = formatDate(meta.fieldworkEnd, { short: true });
    if (meta.minimum === meta.maximum) return `${formatScore(meta.minimum)} · ${date}`;
    return `${formatScore(meta.minimum)}–${formatScore(meta.maximum)} · ${date}`;
  }

  function renderMetrics() {
    const { metrics } = state.data;
    nodes.metricWaves.textContent = formatInteger(metrics.wave_count);
    nodes.hudPollsValue.textContent = formatInteger(metrics.wave_count);
    nodes.metricScenarios.textContent = formatInteger(metrics.scenario_count);
    nodes.metricCandidates.textContent = formatInteger(state.pickerCandidates.length);
    nodes.metricInstitutes.textContent = formatInteger(metrics.institute_count);
    nodes.metricPeriod.textContent = `${formatDate(metrics.period_start, { short: true })} → ${formatDate(metrics.period_end, { short: true })}`;
  }

  function populateInstitutes() {
    const fragment = document.createDocumentFragment();
    for (const institute of state.data.institutes) {
      const option = document.createElement("option");
      option.value = institute.name;
      option.textContent = institute.name;
      fragment.append(option);
    }
    nodes.instituteSelect.append(fragment);
  }

  function visibleCandidateOptions(query = "") {
    const needle = query.trim().toLocaleLowerCase(LOCALE_TAG);
    return state.pickerCandidates
      .filter((candidate) => !state.selectedCandidateIds.includes(candidate.candidate_id))
      .filter((candidate) => {
        if (!needle) return true;
        const searchable = [candidate.candidate_name, ...(candidate.source_labels || [])]
          .join(" ")
          .toLocaleLowerCase(LOCALE_TAG);
        return searchable.includes(needle);
      })
      .slice(0, 24);
  }

  function renderCandidateResults(forceOpen = false) {
    const options = visibleCandidateOptions(nodes.candidateSearch.value);
    nodes.candidateResults.replaceChildren();

    if ((!forceOpen && !nodes.candidateSearch.value.trim()) || options.length === 0 || state.selectedCandidateIds.length >= MAX_SELECTED_CANDIDATES) {
      nodes.candidateResults.hidden = true;
      nodes.candidateSearch.setAttribute("aria-expanded", "false");
      return;
    }

    for (const candidate of options) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "polling-candidate-option";
      button.setAttribute("role", "option");
      button.dataset.candidateId = candidate.candidate_id;

      const name = document.createElement("span");
      name.textContent = candidate.candidate_name;
      const meta = document.createElement("small");
      meta.textContent = pickerMetaText(candidate.candidate_id);
      button.append(name, meta);
      nodes.candidateResults.append(button);
    }

    nodes.candidateResults.hidden = false;
    nodes.candidateSearch.setAttribute("aria-expanded", "true");
  }

  function renderSelectedCandidates() {
    nodes.selectedCandidates.replaceChildren();
    state.selectedCandidateIds.forEach((candidateId, index) => {
      const candidate = candidateById(candidateId);
      if (!candidate) return;
      const chip = document.createElement("span");
      chip.className = "polling-candidate-chip";
      chip.style.setProperty("--candidate-color", SLOT_COLORS[index]);

      const label = document.createElement("span");
      label.textContent = candidate.candidate_name;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.dataset.removeCandidateId = candidateId;
      remove.setAttribute("aria-label", `${uiText("removeCandidate")} ${candidate.candidate_name}`);
      remove.textContent = "×";
      chip.append(label, remove);
      nodes.selectedCandidates.append(chip);
    });

    const full = state.selectedCandidateIds.length >= MAX_SELECTED_CANDIDATES;
    nodes.candidateSearch.disabled = full;
    nodes.candidateAdd.disabled = full;
    nodes.candidateAdd.textContent = full ? uiText("maximumFive") : uiText("addCandidate");
    if (state.data && nodes.inspectorContent) resetInspector();
    renderHistoryChart();
  }

  function addCandidate(candidateId) {
    if (!candidateId || state.selectedCandidateIds.includes(candidateId)) return;
    if (state.selectedCandidateIds.length >= MAX_SELECTED_CANDIDATES) return;
    state.selectedCandidateIds.push(candidateId);
    nodes.candidateSearch.value = "";
    renderSelectedCandidates();
    renderCandidateResults(false);
  }

  function setChartEmpty(title, message, status = uiText("noData")) {
    nodes.historyChart.replaceChildren();
    nodes.historyChart.className = "polling-history-chart";
    nodes.chartReadyState.hidden = false;
    const strong = nodes.chartReadyState.querySelector("strong");
    const span = nodes.chartReadyState.querySelector("span");
    strong.textContent = title;
    span.textContent = message;
    nodes.chartStatus.textContent = status;
  }

  function resetInspector() {
    state.selectedComparableSeriesKey = null;
    state.selectedObservationEventId = null;
    state.selectedObservationCandidateId = null;
    nodes.inspectorContent.className = "polling-inspector-empty";
    nodes.inspectorContent.replaceChildren();
    const strong = document.createElement("strong");
    strong.textContent = uiText("noObservationSelected");
    const paragraph = document.createElement("p");
    paragraph.textContent = uiText("observationInspectorHint");
    nodes.inspectorContent.append(strong, paragraph);
  }

  function periodStartDate() {
    const end = new Date(`${state.data.data_as_of}T00:00:00Z`);
    if (state.period === "all") return new Date(`${state.data.metrics.period_start}T00:00:00Z`);
    const start = new Date(end.getTime());
    if (state.period === "1y") start.setUTCFullYear(start.getUTCFullYear() - 1);
    if (state.period === "6m") start.setUTCMonth(start.getUTCMonth() - 6);
    if (state.period === "3m") start.setUTCMonth(start.getUTCMonth() - 3);
    return start;
  }

  function chartWaves() {
    const start = periodStartDate().getTime();
    const end = new Date(`${state.data.data_as_of}T00:00:00Z`).getTime();
    return state.data.waves
      .filter((wave) => !state.institute || wave.pollster === state.institute)
      .filter((wave) => {
        const date = new Date(`${wave.fieldwork_end}T00:00:00Z`).getTime();
        return date >= start && date <= end;
      })
      .slice()
      .sort((left, right) => left.fieldwork_end.localeCompare(right.fieldwork_end) || left.wave_id.localeCompare(right.wave_id));
  }

  function svgNode(tag, attributes = {}) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
    return node;
  }

  function candidateSlot(candidateId) {
    return state.selectedCandidateIds.indexOf(candidateId);
  }

  function candidateColor(candidateId) {
    const slot = candidateSlot(candidateId);
    return SLOT_COLORS[Math.max(0, slot) % SLOT_COLORS.length];
  }

  function scoreObservationsForWave(wave, candidateId) {
    const observations = [];
    for (const scenario of wave.scenarios) {
      const candidate = scenario.candidates.find(
        (item) => item.identity_type === "person" && item.candidate_id === candidateId && typeof item.score === "number" && Number.isFinite(item.score)
      );
      if (candidate) observations.push({ wave, scenario, candidate });
    }
    return observations;
  }

  function visibleObservations(waves) {
    const observations = [];
    for (const wave of waves) {
      for (const candidateId of state.selectedCandidateIds) {
        observations.push(...scoreObservationsForWave(wave, candidateId));
      }
    }
    return observations;
  }

  function sharedComparableSeriesKey(wave, scenario) {
    return `${wave.pollster}\u0000${scenario.scenario_key}`;
  }

  function selectedCandidatesForScenario(scenario) {
    const candidates = new Map();
    for (const candidateId of state.selectedCandidateIds) {
      const candidate = scenario.candidates.find(
        (item) =>
          item.identity_type === "person" &&
          item.candidate_id === candidateId &&
          typeof item.score === "number" &&
          Number.isFinite(item.score)
      );
      if (!candidate) return null;
      candidates.set(candidateId, candidate);
    }
    return candidates;
  }

  function sharedComparableSeries(waves) {
    const groups = new Map();
    for (const wave of waves) {
      for (const scenario of wave.scenarios) {
        const candidates = selectedCandidatesForScenario(scenario);
        if (!candidates) continue;
        const key = sharedComparableSeriesKey(wave, scenario);
        const group = groups.get(key) || {
          key,
          pollster: wave.pollster,
          scenarioKey: scenario.scenario_key,
          occurrences: [],
        };
        group.occurrences.push({ wave, scenario, candidates });
        groups.set(key, group);
      }
    }

    return [...groups.values()]
      .map((group) => ({
        ...group,
        occurrences: group.occurrences.slice().sort((left, right) =>
          left.wave.fieldwork_end.localeCompare(right.wave.fieldwork_end) ||
          left.scenario.event_id.localeCompare(right.scenario.event_id)
        ),
      }))
      .filter((group) => new Set(group.occurrences.map((item) => item.wave.wave_id)).size >= 2)
      .sort((left, right) => {
        const leftLast = left.occurrences[left.occurrences.length - 1];
        const rightLast = right.occurrences[right.occurrences.length - 1];
        return (
          rightLast.wave.fieldwork_end.localeCompare(leftLast.wave.fieldwork_end) ||
          right.occurrences.length - left.occurrences.length ||
          left.pollster.localeCompare(right.pollster, PAGE_LANG, { sensitivity: "base" }) ||
          left.key.localeCompare(right.key)
        );
      });
  }

  function observationFromOccurrence(occurrence, candidateId) {
    const candidate = occurrence.candidates.get(candidateId);
    return candidate ? { wave: occurrence.wave, scenario: occurrence.scenario, candidate } : null;
  }

  function updateComparableSeriesEmphasis(activeKey = null) {
    if (!nodes.historyChart || state.mode !== "comparable") return;
    const hasActive = Boolean(activeKey);
    for (const group of nodes.historyChart.querySelectorAll(".polling-comparable-series-group")) {
      const matches = hasActive && group.dataset.seriesKey === activeKey;
      group.classList.toggle("is-active", matches);
      group.classList.toggle("is-muted", hasActive && !matches);
    }
    for (const observation of nodes.historyChart.querySelectorAll(".polling-comparable-observation")) {
      observation.classList.toggle(
        "is-selected-observation",
        observation.dataset.eventId === state.selectedObservationEventId &&
          observation.dataset.candidateId === state.selectedObservationCandidateId
      );
    }

    const label = nodes.historyChart.querySelector(".polling-comparable-active-label");
    if (!label) return;
    const selectedGroup = state.selectedComparableSeriesKey
      ? [...nodes.historyChart.querySelectorAll(".polling-comparable-series-group")].find(
          (group) => group.dataset.seriesKey === state.selectedComparableSeriesKey
        ) || null
      : null;
    if (!selectedGroup) {
      label.hidden = true;
      label.textContent = "";
      return;
    }
    label.textContent = `${selectedGroup.dataset.pollster} · ${selectedGroup.dataset.waveCount} ${uiText("waves")} · ${formatDate(selectedGroup.dataset.firstDate, { short: true })} → ${formatDate(selectedGroup.dataset.lastDate, { short: true })}`;
    label.hidden = false;
  }

  function dateTickLabel(timestamp) {
    return new Intl.DateTimeFormat(LOCALE_TAG, { month: "short", year: "2-digit", timeZone: "UTC" }).format(new Date(timestamp));
  }

  function renderInspector(observation, series = null) {
    const { wave, scenario, candidate } = observation;
    nodes.inspectorContent.className = "polling-inspector-detail";
    nodes.inspectorContent.replaceChildren();

    const summary = document.createElement("div");
    summary.className = "polling-inspector-score";
    summary.style.setProperty("--candidate-color", candidateColor(candidate.candidate_id));
    const name = document.createElement("strong");
    name.textContent = candidate.candidate_name;
    const score = document.createElement("span");
    score.textContent = formatScore(candidate.score);
    summary.append(name, score);

    const metadata = document.createElement("dl");
    metadata.className = "polling-inspector-meta";
    const rows = [
      [uiText("pollster"), wave.pollster],
      [uiText("fieldwork"), `${formatDate(wave.fieldwork_start, { short: true })}–${formatDate(wave.fieldwork_end, { short: true })}`],
      [uiText("sample"), wave.sample_size == null ? "—" : `n=${formatInteger(wave.sample_size)}`],
      [uiText("publishedLabel"), candidate.published_candidate_name || candidate.candidate_name],
    ];
    for (const [label, value] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      metadata.append(dt, dd);
    }

    let seriesBlock = null;
    if (series?.occurrences?.length >= 2) {
      const distinctWaveCount = new Set(series.occurrences.map((item) => item.wave.wave_id)).size;
      const first = series.occurrences[0];
      const last = series.occurrences[series.occurrences.length - 1];

      seriesBlock = document.createElement("div");
      seriesBlock.className = "polling-inspector-series";
      const seriesLabel = document.createElement("span");
      seriesLabel.textContent = uiText("repeatedExactBallot");
      const seriesRule = document.createElement("strong");
      seriesRule.textContent = uiText("samePollsterSameScenario");
      const seriesMeta = document.createElement("div");
      seriesMeta.className = "polling-inspector-series-meta";

      const waveCount = document.createElement("span");
      waveCount.textContent = `${distinctWaveCount} ${uiPlural(distinctWaveCount, "wave", "waves")}`;
      const period = document.createElement("span");
      period.textContent = `${formatDate(first.wave.fieldwork_end, { short: true })} → ${formatDate(last.wave.fieldwork_end, { short: true })}`;
      seriesMeta.append(waveCount, period);
      seriesBlock.append(seriesLabel, seriesRule, seriesMeta);
    }

    const scenarioBlock = document.createElement("div");
    scenarioBlock.className = "polling-inspector-scenario";
    const scenarioLabel = document.createElement("span");
    scenarioLabel.textContent = uiText("scenario");
    const scenarioText = document.createElement("p");
    const displayScenarioCandidate = (item) => {
      const label = String(
        item.published_candidate_name
        || item.candidate_name
        || item.label
        || ""
      ).trim();

      return label.replace(/^Generic\s+/i, "");
    };

    const scenarioCandidates = scenario.candidates
      .map(displayScenarioCandidate)
      .filter(Boolean);

    scenarioText.textContent = scenarioCandidates.length
      ? `${uiText("firstRound")} — ${scenarioCandidates.join(", ")}`
      : uiText("firstRound");
    scenarioBlock.append(scenarioLabel, scenarioText);

    const resultBlock = document.createElement("div");
    resultBlock.className = "polling-inspector-results";
    const resultLabel = document.createElement("span");
    resultLabel.textContent = uiText("publishedResults");
    const resultList = document.createElement("div");
    resultList.className = "polling-inspector-result-list";
    for (const item of scenario.candidates) {
      const row = document.createElement("div");
      const resultName = document.createElement("span");
      resultName.textContent = item.published_candidate_name || item.candidate_name;
      const resultScore = document.createElement("strong");
      resultScore.textContent = formatScore(item.score);
      row.append(resultName, resultScore);
      resultList.append(row);
    }
    resultBlock.append(resultLabel, resultList);

    const waveContext = createWavePageLink(
      wave,
      `${wave.pollster} · ${formatDate(
        wave.fieldwork_start,
        { short: true }
      )}–${formatDate(
        wave.fieldwork_end,
        { short: true }
      )}`,
      "polling-inspector-wave-link"
    );

    const openPage = document.createElement("a");
    openPage.className = "polling-inspector-source";

    const pageHref = scenarioPageHref(wave, scenario);

    if (pageHref) {
      openPage.href = pageHref;
      openPage.textContent = uiText("openPoll");
    } else {
      openPage.removeAttribute("href");
      openPage.textContent = uiText("pageUnavailable");
      openPage.setAttribute("aria-disabled", "true");
    }

    nodes.inspectorContent.append(summary, metadata);
    if (seriesBlock) nodes.inspectorContent.append(seriesBlock);
    nodes.inspectorContent.append(
      scenarioBlock,
      resultBlock,
      waveContext,
      openPage
    );
  }

  function renderChartLegend() {
    if (!nodes.chartLegend) return;
    nodes.chartLegend.replaceChildren();
    const items = state.mode === "comparable"
      ? [
          ["legend-dot", uiText("selectedCandidateLegend")],
          ["legend-stem", uiText("sameBallotSameWaveLegend")],
          ["legend-line", uiText("selectedExactRepetitionLegend")],
        ]
      : [
          ["legend-dot", uiText("publishedObservationLegend")],
          ["legend-range", uiText("withinWaveRangeLegend")],
          ["legend-line", uiText("comparableSeriesLegend")],
        ];
    for (const [className, label] of items) {
      const wrapper = document.createElement("span");
      const marker = document.createElement("i");
      marker.className = className;
      marker.setAttribute("aria-hidden", "true");
      wrapper.append(marker, document.createTextNode(` ${label}`));
      nodes.chartLegend.append(wrapper);
    }
  }

  function renderObservationTimeline(waves, observations) {
    nodes.historyChart.className = "polling-history-chart is-timeline";
    const svg = svgNode("svg", {
      class: "polling-history-svg",
      preserveAspectRatio: "none",
      role: "group",
      "aria-label": uiText("publishedObservationsAria"),
    });
    nodes.historyChart.append(svg);

    const chartWidth = Math.max(320, Math.round(nodes.historyChart.clientWidth || 1000));
    const chartHeight = Math.max(280, Math.round(nodes.historyChart.clientHeight || 390));
    svg.setAttribute("viewBox", `0 0 ${chartWidth} ${chartHeight}`);

    const domainStart = periodStartDate().getTime();
    const domainEnd = new Date(`${state.data.data_as_of}T00:00:00Z`).getTime();
    const plotWidth = chartWidth - CHART.left - CHART.right;
    const plotHeight = chartHeight - CHART.top - CHART.bottom;
    const xFor = (iso) => {
      const value = new Date(`${iso}T00:00:00Z`).getTime();
      if (domainEnd === domainStart) return CHART.left + plotWidth / 2;
      return CHART.left + ((value - domainStart) / (domainEnd - domainStart)) * plotWidth;
    };
    const maxObserved = Math.max(...observations.map((item) => item.candidate.score));
    const yMaximum = Math.max(40, Math.ceil(maxObserved / 5) * 5);
    const yFor = (score) => CHART.top + plotHeight - (score / yMaximum) * plotHeight;

    const grid = svgNode("g", { class: "polling-history-grid" });
    for (let score = 0; score <= yMaximum; score += 5) {
      const y = yFor(score);
      grid.append(svgNode("line", { x1: CHART.left, x2: chartWidth - CHART.right, y1: y, y2: y }));
      const label = svgNode("text", { x: CHART.left - 10, y: y + 4, "text-anchor": "end", class: "polling-chart-tick-label" });
      label.textContent = `${score}%`;
      grid.append(label);
    }
    const xTickCount = chartWidth < 520 ? 3 : 5;
    for (let index = 0; index <= xTickCount; index += 1) {
      const timestamp = domainStart + ((domainEnd - domainStart) * index) / xTickCount;
      const x = CHART.left + (plotWidth * index) / xTickCount;
      grid.append(svgNode("line", { x1: x, x2: x, y1: CHART.top, y2: chartHeight - CHART.bottom, class: "polling-chart-vgrid" }));
      const label = svgNode("text", { x, y: chartHeight - 18, "text-anchor": index === 0 ? "start" : index === xTickCount ? "end" : "middle", class: "polling-chart-tick-label" });
      label.textContent = dateTickLabel(timestamp);
      grid.append(label);
    }
    svg.append(grid);

    const appendObservationPoint = (observation) => {
      const candidateId = observation.candidate.candidate_id;
      const x = xFor(observation.wave.fieldwork_end);
      const y = yFor(observation.candidate.score);
      const group = svgNode("g", {
        class: "polling-chart-observation",
        tabindex: "0",
        role: "button",
        "aria-label": `${observation.candidate.candidate_name}, ${formatScore(observation.candidate.score)}, ${observation.wave.pollster}, ${uiText("fieldworkAt")} ${formatDate(observation.wave.fieldwork_end, { short: true })}.`,
      });
      group.dataset.eventId = observation.scenario.event_id;
      const hitTarget = svgNode("circle", { cx: x, cy: y, r: 9, class: "polling-chart-hit-target" });
      const point = svgNode("circle", { cx: x, cy: y, r: 3.7, fill: candidateColor(candidateId), class: "polling-chart-point" });
      const title = svgNode("title");
      title.textContent = `${observation.candidate.candidate_name} · ${formatScore(observation.candidate.score)} · ${observation.wave.pollster} · ${formatDate(observation.wave.fieldwork_end, { short: true })}`;
      point.append(title);
      group.append(hitTarget, point);
      const select = () => {
        state.selectedObservationEventId = observation.scenario.event_id;
        state.selectedObservationCandidateId = observation.candidate.candidate_id;
        state.selectedComparableSeriesKey = null;
        renderInspector(observation);
      };
      group.addEventListener("click", select);
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
      svg.append(group);
    };

    for (const wave of waves) {
      const x = xFor(wave.fieldwork_end);
      for (const candidateId of state.selectedCandidateIds) {
        const waveObservations = scoreObservationsForWave(wave, candidateId);
        if (waveObservations.length < 2) continue;
        const scores = waveObservations.map((item) => item.candidate.score);
        const minimum = Math.min(...scores);
        const maximum = Math.max(...scores);
        if (minimum === maximum) continue;
        svg.append(svgNode("line", {
          x1: x, x2: x, y1: yFor(maximum), y2: yFor(minimum),
          class: "polling-chart-range", stroke: candidateColor(candidateId),
        }));
      }
    }
    for (const observation of observations) appendObservationPoint(observation);
  }

  function renderComparableDumbbellTimeline(series) {
    nodes.historyChart.className = "polling-history-chart is-comparable-timeline";

    const note = document.createElement("div");
    note.className = "polling-comparable-note";
    const noteStrong = document.createElement("strong");
    noteStrong.textContent = uiText("identicalBallotComparison");
    const noteText = document.createElement("span");
    noteText.textContent = uiText("identicalBallotExplanation");
    const activeLabel = document.createElement("span");
    activeLabel.className = "polling-comparable-active-label";
    activeLabel.hidden = true;
    note.append(noteStrong, noteText, activeLabel);
    nodes.historyChart.append(note);

    const svg = svgNode("svg", {
      class: "polling-history-svg polling-comparable-svg",
      preserveAspectRatio: "none",
      role: "group",
      "aria-label": uiText("comparableBallotsAria"),
    });
    nodes.historyChart.append(svg);

    const chartWidth = Math.max(320, Math.round(nodes.historyChart.clientWidth || 1000));
    const chartHeight = Math.max(310, Math.round((nodes.historyChart.clientHeight || 430) - 44));
    svg.setAttribute("viewBox", `0 0 ${chartWidth} ${chartHeight}`);

    const domainStart = periodStartDate().getTime();
    const domainEnd = new Date(`${state.data.data_as_of}T00:00:00Z`).getTime();
    const plotWidth = chartWidth - CHART.left - CHART.right;
    const plotHeight = chartHeight - CHART.top - CHART.bottom;
    const xFor = (iso) => {
      const value = new Date(`${iso}T00:00:00Z`).getTime();
      if (domainEnd === domainStart) return CHART.left + plotWidth / 2;
      return CHART.left + ((value - domainStart) / (domainEnd - domainStart)) * plotWidth;
    };

    const allScores = series.flatMap((group) =>
      group.occurrences.flatMap((occurrence) =>
        state.selectedCandidateIds.map((candidateId) => occurrence.candidates.get(candidateId)?.score).filter(Number.isFinite)
      )
    );
    const maxObserved = Math.max(...allScores);
    const yMaximum = Math.max(40, Math.ceil(maxObserved / 5) * 5);
    const yFor = (score) => CHART.top + plotHeight - (score / yMaximum) * plotHeight;

    const grid = svgNode("g", { class: "polling-history-grid" });
    for (let score = 0; score <= yMaximum; score += 5) {
      const y = yFor(score);
      grid.append(svgNode("line", { x1: CHART.left, x2: chartWidth - CHART.right, y1: y, y2: y }));
      const label = svgNode("text", { x: CHART.left - 10, y: y + 4, "text-anchor": "end", class: "polling-chart-tick-label" });
      label.textContent = `${score}%`;
      grid.append(label);
    }
    const xTickCount = chartWidth < 520 ? 3 : 5;
    for (let index = 0; index <= xTickCount; index += 1) {
      const timestamp = domainStart + ((domainEnd - domainStart) * index) / xTickCount;
      const x = CHART.left + (plotWidth * index) / xTickCount;
      grid.append(svgNode("line", { x1: x, x2: x, y1: CHART.top, y2: chartHeight - CHART.bottom, class: "polling-chart-vgrid" }));
      const label = svgNode("text", { x, y: chartHeight - 18, "text-anchor": index === 0 ? "start" : index === xTickCount ? "end" : "middle", class: "polling-chart-tick-label" });
      label.textContent = dateTickLabel(timestamp);
      grid.append(label);
    }
    svg.append(grid);

    const availableSeriesKeys = new Set();
    for (const sharedSeries of series) {
      availableSeriesKeys.add(sharedSeries.key);
      const seriesGroup = svgNode("g", { class: "polling-comparable-series-group" });
      seriesGroup.dataset.seriesKey = sharedSeries.key;
      seriesGroup.dataset.pollster = sharedSeries.pollster;
      seriesGroup.dataset.waveCount = String(sharedSeries.occurrences.length);
      seriesGroup.dataset.firstDate = sharedSeries.occurrences[0].wave.fieldwork_end;
      seriesGroup.dataset.lastDate = sharedSeries.occurrences[sharedSeries.occurrences.length - 1].wave.fieldwork_end;

      for (const candidateId of state.selectedCandidateIds) {
        const path = [];
        for (const occurrence of sharedSeries.occurrences) {
          const candidate = occurrence.candidates.get(candidateId);
          if (!candidate) continue;
          path.push(`${xFor(occurrence.wave.fieldwork_end)},${yFor(candidate.score)}`);
        }
        if (path.length >= 2) {
          seriesGroup.append(svgNode("polyline", {
            points: path.join(" "),
            fill: "none",
            stroke: candidateColor(candidateId),
            class: "polling-comparable-series-path",
          }));
        }
      }

      for (const occurrence of sharedSeries.occurrences) {
        const x = xFor(occurrence.wave.fieldwork_end);
        const scores = state.selectedCandidateIds
          .map((candidateId) => occurrence.candidates.get(candidateId)?.score)
          .filter(Number.isFinite);
        if (scores.length === 0) continue;
        const minimum = Math.min(...scores);
        const maximum = Math.max(...scores);
        const occurrenceGroup = svgNode("g", { class: "polling-comparable-occurrence" });
        occurrenceGroup.dataset.seriesKey = sharedSeries.key;

        const hitStem = svgNode("line", {
          x1: x,
          x2: x,
          y1: yFor(maximum),
          y2: yFor(minimum),
          class: "polling-comparable-stem-hit",
        });
        const stem = svgNode("line", {
          x1: x,
          x2: x,
          y1: yFor(maximum),
          y2: yFor(minimum),
          class: "polling-comparable-stem",
        });
        occurrenceGroup.append(hitStem, stem);

        const previewSeries = () => updateComparableSeriesEmphasis(sharedSeries.key);
        const selectSeries = () => {
          state.selectedComparableSeriesKey = sharedSeries.key;
          state.selectedObservationEventId = null;
          state.selectedObservationCandidateId = null;
          updateComparableSeriesEmphasis(sharedSeries.key);
        };
        occurrenceGroup.addEventListener("mouseenter", previewSeries);
        occurrenceGroup.addEventListener("mouseleave", () => updateComparableSeriesEmphasis(state.selectedComparableSeriesKey));
        hitStem.addEventListener("click", selectSeries);

        for (const candidateId of state.selectedCandidateIds) {
          const observation = observationFromOccurrence(occurrence, candidateId);
          if (!observation) continue;
          const y = yFor(observation.candidate.score);
          const pointGroup = svgNode("g", {
            class: "polling-comparable-observation",
            tabindex: "0",
            role: "button",
            "aria-label": `${observation.candidate.candidate_name}, ${formatScore(observation.candidate.score)}, ${observation.wave.pollster}, ${uiText("fieldworkAt")} ${formatDate(observation.wave.fieldwork_end, { short: true })}.`,
          });
          pointGroup.dataset.eventId = observation.scenario.event_id;
          pointGroup.dataset.candidateId = candidateId;
          pointGroup.dataset.seriesKey = sharedSeries.key;

          const hitTarget = svgNode("circle", { cx: x, cy: y, r: 10, class: "polling-chart-hit-target" });
          const point = svgNode("circle", { cx: x, cy: y, r: 4.2, fill: candidateColor(candidateId), class: "polling-chart-point" });
          const title = svgNode("title");
          title.textContent = `${observation.candidate.candidate_name} · ${formatScore(observation.candidate.score)} · ${observation.wave.pollster} · ${formatDate(observation.wave.fieldwork_end, { short: true })}`;
          point.append(title);
          pointGroup.append(hitTarget, point);

          const select = () => {
            state.selectedObservationEventId = observation.scenario.event_id;
            state.selectedObservationCandidateId = candidateId;
            state.selectedComparableSeriesKey = sharedSeries.key;
            updateComparableSeriesEmphasis(sharedSeries.key);
            renderInspector(observation, sharedSeries);
          };
          pointGroup.addEventListener("click", select);
          pointGroup.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              select();
            }
          });
          pointGroup.addEventListener("focus", previewSeries);
          pointGroup.addEventListener("blur", () => updateComparableSeriesEmphasis(state.selectedComparableSeriesKey));
          occurrenceGroup.append(pointGroup);
        }
        seriesGroup.append(occurrenceGroup);
      }
      svg.append(seriesGroup);
    }

    if (state.selectedComparableSeriesKey && !availableSeriesKeys.has(state.selectedComparableSeriesKey)) {
      resetInspector();
    }
    updateComparableSeriesEmphasis(state.selectedComparableSeriesKey);
  }

  function renderHistoryChart() {
    if (!state.data || !nodes.historyChart) return;
    renderChartLegend();
    if (state.selectedCandidateIds.length === 0) {
      setChartEmpty(uiText("selectUpToFive"), uiText("publishedObservationsAppearHere"), uiText("selectionRequired"));
      resetInspector();
      return;
    }

    const waves = chartWaves();
    const observations = visibleObservations(waves);
    const series = state.mode === "comparable" ? sharedComparableSeries(waves) : [];
    if ((state.mode === "comparable" && series.length === 0) || (state.mode !== "comparable" && observations.length === 0)) {
      const message = state.mode === "comparable"
        ? uiText("noComparableForFilters")
        : uiText("noObservationForFilters");
      setChartEmpty(uiText("noDataToDisplay"), message);
      resetInspector();
      return;
    }

    nodes.chartReadyState.hidden = true;
    nodes.historyChart.replaceChildren();
    if (state.mode === "comparable") {
      renderComparableDumbbellTimeline(series);
      const comparableWaveCount = series.reduce((total, group) => total + group.occurrences.length, 0);
      nodes.chartStatus.textContent = `${comparableWaveCount} ${uiPlural(comparableWaveCount, "wave", "waves")} ${uiPlural(comparableWaveCount, "shared", "sharedPlural")} · ${series.length} ${uiPlural(series.length, "exactBallot", "exactBallots")}`;
    } else {
      renderObservationTimeline(waves, observations);
      nodes.chartStatus.textContent = `${observations.length} ${uiPlural(observations.length, "observation", "observations")}`;
    }
  }

  function setSegment(group, value) {
    const wrapper = document.querySelector(`[data-control="${group}"]`);
    if (!wrapper) return;
    for (const button of wrapper.querySelectorAll("button[data-value]")) {
      button.setAttribute("aria-pressed", String(button.dataset.value === value));
    }
    state[group] = value;
  }

  function rangeRowsForWave(wave) {
    const observed = new Map();
    for (const scenario of wave.scenarios) {
      for (const candidate of scenario.candidates) {
        if (candidate.identity_type !== "person") continue;
        if (typeof candidate.score !== "number" || !Number.isFinite(candidate.score)) continue;
        const row = observed.get(candidate.candidate_id) || {
          candidateId: candidate.candidate_id,
          candidateName: candidate.candidate_name,
          scores: [],
        };
        row.scores.push(candidate.score);
        observed.set(candidate.candidate_id, row);
      }
    }

    return [...observed.values()]
      .map((row) => {
        const minimum = Math.min(...row.scores);
        const maximum = Math.max(...row.scores);
        return {
          ...row,
          minimum,
          maximum,
          range: maximum - minimum,
          scenarioCount: row.scores.length,
        };
      })
      .sort((a, b) => a.candidateName.localeCompare(b.candidateName, PAGE_LANG, { sensitivity: "base" }));
  }

  function populateWaveSelector() {
    nodes.waveSelect.replaceChildren();
    for (const wave of state.data.waves) {
      const option = document.createElement("option");
      option.value = wave.wave_id;
      option.textContent = `${wave.pollster} · ${formatDate(wave.fieldwork_end, { short: true })} · ${wave.scenario_count} ${uiPlural(wave.scenario_count, "scenarioLower", "scenariosLower")}`;
      nodes.waveSelect.append(option);
    }

    const defaultWave = state.data.waves.find((wave) => wave.scenario_count >= 2) || state.data.waves[0] || null;
    state.rangeWaveId = defaultWave?.wave_id || null;
    if (state.rangeWaveId) nodes.waveSelect.value = state.rangeWaveId;
    renderRangeWave();
  }

  function renderRangeWave() {
    const wave = state.data.waves.find((item) => item.wave_id === state.rangeWaveId);
    nodes.rangeList.replaceChildren();
    if (!wave) {
      nodes.rangeContext.textContent = uiText("noWaveAvailable");
      return;
    }

    const rows = rangeRowsForWave(wave);
    const scaleMaximum = Math.max(5, Math.ceil(Math.max(...rows.map((row) => row.maximum), 0) / 5) * 5);
    nodes.rangeContext.textContent = `${wave.pollster} · ${uiText("fieldworkLower")} ${formatDate(wave.fieldwork_start, { short: true })}–${formatDate(wave.fieldwork_end, { short: true })} · ${wave.scenario_count} ${uiPlural(wave.scenario_count, "scenarioLower", "scenariosLower")} · n=${wave.sample_size ?? "—"}`;

    for (const row of rows) {
      const wrapper = document.createElement("div");
      wrapper.className = "polling-range-row";
      wrapper.setAttribute(
        "aria-label",
        `${row.candidateName} : ${uiText("minimumLower")} ${formatScore(row.minimum)}, ${uiText("maximumLower")} ${formatScore(row.maximum)}, ${uiText("rangeLower")} ${formatPoints(row.range)}, ${uiText("testedInLower")} ${row.scenarioCount} ${uiPlural(row.scenarioCount, "scenarioLower", "scenariosLower")}.`
      );

      const name = document.createElement("div");
      name.className = "polling-range-name";
      name.textContent = row.candidateName;

      const minimum = document.createElement("div");
      minimum.className = "polling-range-value min";
      minimum.textContent = formatScore(row.minimum);

      const track = document.createElement("div");
      track.className = "polling-range-track";
      track.setAttribute("aria-hidden", "true");
      const leftPercent = (row.minimum / scaleMaximum) * 100;
      const rightPercent = (row.maximum / scaleMaximum) * 100;
      const stem = document.createElement("span");
      stem.className = "polling-range-stem";
      stem.style.left = `${leftPercent}%`;
      stem.style.width = `${Math.max(0, rightPercent - leftPercent)}%`;
      const startPoint = document.createElement("span");
      startPoint.className = "polling-range-point";
      startPoint.style.left = `${leftPercent}%`;
      track.append(stem, startPoint);
      if (row.maximum !== row.minimum) {
        const endPoint = document.createElement("span");
        endPoint.className = "polling-range-point end";
        endPoint.style.left = `${rightPercent}%`;
        track.append(endPoint);
      }

      const maximum = document.createElement("div");
      maximum.className = "polling-range-value max";
      maximum.textContent = formatScore(row.maximum);

      const delta = document.createElement("div");
      delta.className = "polling-range-delta";
      delta.textContent = row.scenarioCount === 1 ? uiText("uniqueValue") : formatPoints(row.range);

      const tested = document.createElement("div");
      tested.className = "polling-range-tested";
      tested.textContent = `${row.scenarioCount} ${uiPlural(row.scenarioCount, "scenarioLower", "scenariosLower")}`;

      wrapper.append(name, minimum, track, maximum, delta, tested);
      nodes.rangeList.append(wrapper);
    }
  }

  function openCellForWave(wave) {
    const cell = document.createElement("div");
    cell.className = "polling-wave-source-cell";

    cell.append(
      createWavePageLink(
        wave,
        uiText("openPoll"),
        "polling-wave-open-link"
      )
    );

    return cell;
  }

  function renderLatestWaves() {
    nodes.latestWaveDirectory.replaceChildren();
    const table = document.createElement("table");
    table.className = "polling-wave-table";
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    [uiText("fieldwork"), uiText("pollster"), uiText("scenarios"), uiText("sample"), uiText("candidates"), uiText("pollPage")].forEach((label) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = label;
      headerRow.append(th);
    });
    thead.append(headerRow);

    const tbody = document.createElement("tbody");
    for (const wave of state.data.waves.slice(0, LATEST_WAVE_LIMIT)) {
      const row = document.createElement("tr");
      const values = [
        `${formatDate(wave.fieldwork_start, { short: true })}–${formatDate(wave.fieldwork_end, { short: true })}`,
        wave.pollster,
        formatInteger(wave.scenario_count),
        wave.sample_size == null ? "—" : formatInteger(wave.sample_size),
        formatInteger(wave.candidate_ids.length),
      ];
      const labels = [uiText("fieldwork"), uiText("pollster"), uiText("scenarios"), uiText("sample"), uiText("candidates")];
      values.forEach((value, index) => {
        const cell = document.createElement("td");
        cell.dataset.label = labels[index];

        if (index <= 1) {
          cell.append(
            createWavePageLink(
              wave,
              value
            )
          );
        } else {
          cell.textContent = value;
        }

        row.append(cell);
      });
      const sourceCell = document.createElement("td");
      sourceCell.dataset.label = uiText("pollPage");
      sourceCell.append(openCellForWave(wave));
      row.append(sourceCell);
      tbody.append(row);
    }

    table.append(thead, tbody);
    nodes.latestWaveDirectory.append(table);
  }

  function buildBrowseWaveTable(waves) {
    const table = document.createElement("table");
    table.className = "polling-wave-table polling-browse-wave-table";
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    [uiText("fieldwork"), uiText("pollster"), uiText("scenarios"), uiText("sample"), uiText("candidates"), uiText("pollPage")].forEach((label) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = label;
      headerRow.append(th);
    });
    thead.append(headerRow);

    const tbody = document.createElement("tbody");
    for (const wave of waves) {
      const row = document.createElement("tr");
      const values = [
        `${formatDate(wave.fieldwork_start, { short: true })}–${formatDate(wave.fieldwork_end, { short: true })}`,
        wave.pollster,
        formatInteger(wave.scenario_count),
        wave.sample_size == null ? "—" : formatInteger(wave.sample_size),
        formatInteger(wave.candidate_ids.length),
      ];
      const labels = [uiText("fieldwork"), uiText("pollster"), uiText("scenarios"), uiText("sample"), uiText("candidates")];
      values.forEach((value, index) => {
        const cell = document.createElement("td");
        cell.dataset.label = labels[index];

        if (index <= 1) {
          cell.append(
            createWavePageLink(
              wave,
              value
            )
          );
        } else {
          cell.textContent = value;
        }

        row.append(cell);
      });
      const sourceCell = document.createElement("td");
      sourceCell.dataset.label = uiText("pollPage");
      sourceCell.append(openCellForWave(wave));
      row.append(sourceCell);
      tbody.append(row);
    }
    table.append(thead, tbody);
    return table;
  }

  function candidateBrowseWaves(candidateId) {
    return state.data.waves.filter((wave) =>
      wave.scenarios.some((scenario) =>
        scenario.candidates.some(
          (candidate) => candidate.identity_type === "person" && candidate.candidate_id === candidateId
        )
      )
    );
  }

  function candidateWaveScoreMeta(wave, candidateId) {
    const scores = [];
    for (const scenario of wave.scenarios) {
      const candidate = scenario.candidates.find(
        (item) => item.identity_type === "person" && item.candidate_id === candidateId && typeof item.score === "number" && Number.isFinite(item.score)
      );
      if (candidate) scores.push(candidate.score);
    }
    if (scores.length === 0) return null;
    return {
      minimum: Math.min(...scores),
      maximum: Math.max(...scores),
      scenarioCount: scores.length,
    };
  }

  function renderBrowseAll() {
    const wrapper = document.createElement("div");
    wrapper.className = "polling-browse-content";

    const summary = document.createElement("div");
    summary.className = "polling-browse-summary";
    summary.innerHTML = `<strong>${formatInteger(state.data.metrics.wave_count)} ${uiPlural(state.data.metrics.wave_count, "wave", "waves")} · ${formatInteger(state.data.metrics.scenario_count)} ${uiPlural(state.data.metrics.scenario_count, "scenario", "scenarios")}</strong><span>${formatDate(state.data.metrics.period_start, { short: true })} → ${formatDate(state.data.metrics.period_end, { short: true })}</span>`;
    wrapper.append(summary);

    const visible = state.data.waves.slice(0, state.browseWaveLimit);
    wrapper.append(buildBrowseWaveTable(visible));

    if (state.data.waves.length > 15) {
      const action = document.createElement("button");
      action.type = "button";
      action.className = "polling-browse-more";
      action.dataset.browseAction = "toggle-all-waves";
      const expanded = state.browseWaveLimit >= state.data.waves.length;
      action.textContent = expanded
        ? uiText("collapseDirectory")
        : `${uiText("showRemainingPrefix")} ${formatInteger(state.data.waves.length - visible.length)} ${uiText("remainingWaves")}`;
      wrapper.append(action);
    }
    nodes.browsePanel.append(wrapper);
  }

  function renderBrowseInstitutes() {
    const wrapper = document.createElement("div");
    wrapper.className = "polling-browse-content";
    const grid = document.createElement("div");
    grid.className = "polling-browse-index-grid";

    for (const institute of state.data.institutes) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "polling-browse-index-card";
      button.dataset.browseInstitute = institute.name;
      button.setAttribute("aria-pressed", String(state.browseInstitute === institute.name));
      const title = document.createElement("strong");
      title.textContent = institute.name;
      const counts = document.createElement("span");
      counts.textContent = `${formatInteger(institute.wave_count)} ${uiPlural(institute.wave_count, "waveLower", "wavesLower")} · ${formatInteger(institute.scenario_count)} ${uiPlural(institute.scenario_count, "scenarioLower", "scenariosLower")}`;
      const period = document.createElement("small");
      period.textContent = `${formatDate(institute.first_observed, { short: true })} → ${formatDate(institute.last_observed, { short: true })}`;
      button.append(title, counts, period);
      grid.append(button);
    }
    wrapper.append(grid);

    if (state.browseInstitute) {
      const waves = state.data.waves.filter((wave) => wave.pollster === state.browseInstitute);
      const detail = document.createElement("div");
      detail.className = "polling-browse-detail";
      const head = document.createElement("div");
      head.className = "polling-browse-detail-head";
      const title = document.createElement("strong");
      title.textContent = state.browseInstitute;
      const meta = document.createElement("span");
      meta.textContent = `${formatInteger(waves.length)} ${uiPlural(waves.length, "waveLower", "wavesLower")}`;
      head.append(title, meta);
      detail.append(head, buildBrowseWaveTable(waves));
      wrapper.append(detail);
    } else {
      const hint = document.createElement("p");
      hint.className = "polling-browse-hint";
      hint.textContent = uiText("selectInstitute");
      wrapper.append(hint);
    }
    nodes.browsePanel.append(wrapper);
  }

  function renderCandidateBrowseDetail(candidateId) {
    const candidate = candidateById(candidateId);
    if (!candidate) return null;
    const waves = candidateBrowseWaves(candidateId);
    const detail = document.createElement("div");
    detail.className = "polling-browse-detail polling-browse-candidate-detail";

    const head = document.createElement("div");
    head.className = "polling-browse-detail-head";
    const identity = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = candidate.candidate_name;
    const latest = state.latestPollMetaByCandidate.get(candidateId);
    const meta = document.createElement("span");
    meta.textContent = latest
      ? `${pickerMetaText(candidateId)} · ${formatInteger(waves.length)} ${uiPlural(waves.length, "waveLower", "wavesLower")}`
      : `${formatInteger(waves.length)} ${uiPlural(waves.length, "waveLower", "wavesLower")}`;
    identity.append(title, meta);
    const add = document.createElement("button");
    add.type = "button";
    add.className = "polling-browse-compare";
    add.dataset.browseCompareCandidate = candidateId;
    add.disabled = state.selectedCandidateIds.includes(candidateId) || state.selectedCandidateIds.length >= MAX_SELECTED_CANDIDATES;
    add.textContent = state.selectedCandidateIds.includes(candidateId) ? uiText("alreadySelected") : uiText("addToComparison");
    head.append(identity, add);
    detail.append(head);

    const rows = document.createElement("div");
    rows.className = "polling-browse-candidate-waves";
    for (const wave of waves) {
      const scoreMeta = candidateWaveScoreMeta(wave, candidateId);
      if (!scoreMeta) continue;
      const row = document.createElement("div");
      row.className = "polling-browse-candidate-wave";
      const date = document.createElement("span");
      date.append(
        createWavePageLink(
          wave,
          formatDate(wave.fieldwork_end, { short: true })
        )
      );

      const pollster = document.createElement("strong");
      pollster.append(
        createWavePageLink(
          wave,
          wave.pollster
        )
      );
      const score = document.createElement("span");
      score.textContent = scoreMeta.minimum === scoreMeta.maximum
        ? formatScore(scoreMeta.minimum)
        : `${formatScore(scoreMeta.minimum)}–${formatScore(scoreMeta.maximum)}`;
      const tested = document.createElement("small");
      tested.textContent = `${scoreMeta.scenarioCount} ${uiPlural(scoreMeta.scenarioCount, "scenarioLower", "scenariosLower")}`;
      row.append(date, pollster, score, tested);
      rows.append(row);
    }
    detail.append(rows);
    return detail;
  }

  function renderBrowseCandidates() {
    const wrapper = document.createElement("div");
    wrapper.className = "polling-browse-content";
    const grid = document.createElement("div");
    grid.className = "polling-browse-candidate-grid";

    for (const candidate of state.pickerCandidates) {
      const meta = state.latestPollMetaByCandidate.get(candidate.candidate_id);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "polling-browse-candidate-card";
      button.dataset.browseCandidate = candidate.candidate_id;
      button.setAttribute("aria-pressed", String(state.browseCandidateId === candidate.candidate_id));
      const name = document.createElement("strong");
      name.textContent = candidate.candidate_name;
      const score = document.createElement("span");
      score.textContent = pickerMetaText(candidate.candidate_id);
      const waves = document.createElement("small");
      waves.textContent = `${formatInteger(candidate.wave_count)} ${uiPlural(candidate.wave_count, "waveLower", "wavesLower")}`;
      if (!meta) score.textContent = uiText("noObservation");
      button.append(name, score, waves);
      grid.append(button);
    }
    wrapper.append(grid);

    if (state.browseCandidateId) {
      const detail = renderCandidateBrowseDetail(state.browseCandidateId);
      if (detail) wrapper.append(detail);
    } else {
      const hint = document.createElement("p");
      hint.className = "polling-browse-hint";
      hint.textContent = uiText("selectCandidate");
      wrapper.append(hint);
    }
    nodes.browsePanel.append(wrapper);
  }

  function renderBrowseExplorer() {
    if (!state.data || !nodes.browsePanel) return;
    nodes.browsePanel.replaceChildren();
    for (const button of nodes.browseTabs.querySelectorAll("button[data-browse-mode]")) {
      button.setAttribute("aria-selected", String(button.dataset.browseMode === state.browseMode));
    }
    nodes.browseCountAll.textContent = `${formatInteger(state.data.metrics.wave_count)} ${uiPlural(state.data.metrics.wave_count, "wave", "waves")}`;
    nodes.browseCountInstitutes.textContent = `${formatInteger(state.data.metrics.institute_count)} ${uiPlural(state.data.metrics.institute_count, "pollster", "pollsters")}`;
    nodes.browseCountCandidates.textContent = `${formatInteger(state.pickerCandidates.length)} ${uiPlural(state.pickerCandidates.length, "candidate", "candidates")}`;

    if (state.browseMode === "institutes") renderBrowseInstitutes();
    else if (state.browseMode === "candidates") renderBrowseCandidates();
    else renderBrowseAll();
  }

  function resetControls() {
    state.selectedCandidateIds = [];
    state.institute = "";
    nodes.instituteSelect.value = "";
    nodes.candidateSearch.value = "";
    setSegment("period", "all");
    setSegment("mode", "observations");
    renderSelectedCandidates();
    renderCandidateResults(false);
  }

  function bindEvents() {
    nodes.candidateSearch.addEventListener("input", () => renderCandidateResults(true));
    nodes.candidateSearch.addEventListener("focus", () => renderCandidateResults(true));
    nodes.candidateAdd.addEventListener("click", () => {
      nodes.candidateSearch.focus();
      renderCandidateResults(true);
    });

    nodes.candidateResults.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-candidate-id]");
      if (button) addCandidate(button.dataset.candidateId);
    });

    nodes.selectedCandidates.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-remove-candidate-id]");
      if (!button) return;
      state.selectedCandidateIds = state.selectedCandidateIds.filter((candidateId) => candidateId !== button.dataset.removeCandidateId);
      renderSelectedCandidates();
    });

    document.addEventListener("click", (event) => {
      if (!event.target.closest(".polling-candidate-picker")) {
        nodes.candidateResults.hidden = true;
        nodes.candidateSearch.setAttribute("aria-expanded", "false");
      }
    });

    for (const group of ["period", "mode"]) {
      const wrapper = document.querySelector(`[data-control="${group}"]`);
      wrapper?.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-value]");
        if (button) {
          setSegment(group, button.dataset.value);
          resetInspector();
          renderHistoryChart();
        }
      });
    }

    nodes.instituteSelect.addEventListener("change", () => {
      state.institute = nodes.instituteSelect.value;
      resetInspector();
      renderHistoryChart();
    });

    nodes.waveSelect.addEventListener("change", () => {
      state.rangeWaveId = nodes.waveSelect.value;
      renderRangeWave();
    });

    nodes.browseTabs.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-browse-mode]");
      if (!button) return;
      state.browseMode = button.dataset.browseMode;
      state.browseWaveLimit = 15;
      renderBrowseExplorer();
    });

    nodes.browsePanel.addEventListener("click", (event) => {
      const action = event.target.closest("button[data-browse-action]");
      if (action?.dataset.browseAction === "toggle-all-waves") {
        state.browseWaveLimit = state.browseWaveLimit >= state.data.waves.length ? 15 : state.data.waves.length;
        renderBrowseExplorer();
        return;
      }
      const institute = event.target.closest("button[data-browse-institute]");
      if (institute) {
        state.browseInstitute = state.browseInstitute === institute.dataset.browseInstitute ? "" : institute.dataset.browseInstitute;
        renderBrowseExplorer();
        return;
      }
      const candidate = event.target.closest("button[data-browse-candidate]");
      if (candidate) {
        state.browseCandidateId = state.browseCandidateId === candidate.dataset.browseCandidate ? "" : candidate.dataset.browseCandidate;
        renderBrowseExplorer();
        return;
      }
      const compare = event.target.closest("button[data-browse-compare-candidate]");
      if (compare) {
        addCandidate(compare.dataset.browseCompareCandidate);
        renderBrowseExplorer();
      }
    });

    nodes.resetControls.addEventListener("click", resetControls);

    let resizeTimer = null;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(renderHistoryChart, 100);
    });
  }

  function cacheNodes() {
    Object.assign(nodes, {
      metricWaves: byId("metric-waves"),
      metricScenarios: byId("metric-scenarios"),
      metricCandidates: byId("metric-candidates"),
      metricInstitutes: byId("metric-institutes"),
      metricPeriod: byId("metric-period"),
      hudPollsValue: byId("fr27-hud-polls-value"),
      candidateSearch: byId("candidate-search"),
      candidateAdd: byId("candidate-add"),
      candidateResults: byId("candidate-results"),
      selectedCandidates: byId("selected-candidates"),
      instituteSelect: byId("institute-select"),
      waveSelect: byId("wave-select"),
      rangeContext: byId("range-context"),
      rangeList: byId("range-list"),
      latestWaveDirectory: byId("latest-wave-directory"),
      browseTabs: byId("polling-browse-tabs"),
      browsePanel: byId("polling-browse-panel"),
      browseCountAll: byId("browse-count-all"),
      browseCountInstitutes: byId("browse-count-institutes"),
      browseCountCandidates: byId("browse-count-candidates"),
      resetControls: byId("reset-controls"),
      historyChart: byId("polling-history-chart"),
      chartLegend: byId("polling-chart-legend"),
      chartReadyState: byId("chart-ready-state"),
      chartStatus: byId("chart-status"),
      inspectorContent: byId("inspector-content"),
      error: byId("polling-error"),
    });
  }

  function showError(error) {
    nodes.error.hidden = false;
    nodes.error.textContent = `${uiText("loadFailure")} ${error instanceof Error ? error.message : String(error)}`;
    nodes.rangeContext.textContent = uiText("dataUnavailable");
  }

  async function init() {
    cacheNodes();
    bindEvents();
    try {
      const [pollResponse, candidateResponse] = await Promise.all([
        fetch(DATA_URL, { cache: "no-store" }),
        fetch(CANDIDATE_SIGNALS_URL, { cache: "no-store" }),
      ]);
      if (!pollResponse.ok) throw new Error(`${uiText("pollHttpError")} ${pollResponse.status}.`);
      if (!candidateResponse.ok) throw new Error(`${uiText("candidateUniverseHttpError")} ${candidateResponse.status}.`);
      state.data = validateData(await pollResponse.json());
      state.activeCandidateIds = validateCandidateSignals(await candidateResponse.json());
      state.pickerCandidates = buildPickerCandidates();
      renderMetrics();
      populateInstitutes();
      renderSelectedCandidates();
      populateWaveSelector();
      renderLatestWaves();
      renderBrowseExplorer();
    } catch (error) {
      showError(error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();


/* === FR27 STANDALONE SHELL: exact candidate-page header/footer behavior === */
(() => {
  "use strict";

  const shellLanguage = document.documentElement.lang.toLowerCase().startsWith("en") ? "en" : "fr";
  const localeTag = shellLanguage === "en" ? "en-GB" : "fr-FR";
  const formatNumber = value => new Intl.NumberFormat(localeTag).format(value);
  const shellText = (fr, en) => shellLanguage === "en" ? en : fr;

  const initClocks = () => {
    const election = new Date("2027-04-18T00:00:00+02:00");
    const countdown = document.querySelector("[data-countdown] .candidate-countdown-value");
    const hudCountdown = document.getElementById("fr27-hud-countdown-days");
    const refreshCountdown = () => {
      const days = Math.max(
        0,
        Math.ceil((election.getTime() - Date.now()) / 86400000)
      );
      if (countdown) countdown.textContent = formatNumber(days);
      if (hudCountdown) hudCountdown.textContent = formatNumber(days);
    };
    refreshCountdown();
    window.setInterval(refreshCountdown, 60000);
  };

  const initApplicationHud = () => {
    const hud = document.querySelector("#candidate-app-hud.fr27-app-hud");
    if (!hud) return;

    const shell = hud.closest(".polling-shell") || document.querySelector(".polling-shell");
    const toggle = hud.querySelector("#fr27-app-hud-toggle");
    const content = hud.querySelector(".fr27-app-hud-content");
    const emailToggle = hud.querySelector("#fr27-hud-email-toggle");
    const contactPopover = hud.querySelector("#fr27-hud-contact-popover");
    const contactCopy = hud.querySelector("#fr27-hud-contact-copy");
    const infoToggle = hud.querySelector("#fr27-hud-info-toggle");
    const infoPopover = hud.querySelector("#fr27-hud-info-popover");
    const root = document.body;
    if (!shell || !toggle || !content || !root) return;

    let expanded = true;

    const syncHudGeometry = () => {
      const rect = shell.getBoundingClientRect();
      const style = window.getComputedStyle(shell);
      const paddingLeft = Number.parseFloat(style.paddingLeft) || 0;
      const paddingRight = Number.parseFloat(style.paddingRight) || 0;
      const left = rect.left + paddingLeft;
      const width = Math.max(0, rect.width - paddingLeft - paddingRight);
      hud.style.setProperty("--fr27-app-hud-left", `${left.toFixed(2)}px`);
      hud.style.setProperty("--fr27-app-hud-width", `${width.toFixed(2)}px`);
    };

    const setInfoOpen = open => {
      if (!infoToggle || !infoPopover) return;
      infoToggle.setAttribute("aria-expanded", String(open));
      infoPopover.setAttribute("aria-hidden", String(!open));
    };
    const closeInfo = () => setInfoOpen(false);

    const setContactOpen = open => {
      if (!emailToggle || !contactPopover) return;
      emailToggle.setAttribute("aria-expanded", String(open));
      contactPopover.setAttribute("aria-hidden", String(!open));
    };
    const closeContact = () => setContactOpen(false);

    const renderHudState = () => {
      hud.dataset.expanded = expanded ? "true" : "false";
      root.classList.toggle("fr27-app-hud-collapsed", !expanded);
      toggle.setAttribute("aria-expanded", String(expanded));
      const label = expanded
        ? shellText("Réduire le dock système", "Collapse system dock")
        : shellText("Développer le dock système", "Expand system dock");
      toggle.setAttribute("aria-label", label);
      toggle.dataset.fr27Tooltip = label;
      content.setAttribute("aria-hidden", String(!expanded));
      if ("inert" in content) content.inert = !expanded;
      if (!expanded) {
        closeContact();
        closeInfo();
      }
    };

    const timeNode = hud.querySelector("#fr27-hud-paris-time");
    const dateNode = hud.querySelector("#fr27-hud-paris-date");
    const zoneNode = hud.querySelector("#fr27-hud-paris-zone");
    const timeFormatter = new Intl.DateTimeFormat(localeTag, {
      timeZone: "Europe/Paris",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23"
    });
    const dateFormatter = new Intl.DateTimeFormat(localeTag, {
      timeZone: "Europe/Paris",
      day: "2-digit",
      month: "short",
      year: "numeric"
    });
    const zoneFormatter = new Intl.DateTimeFormat(localeTag, {
      timeZone: "Europe/Paris",
      timeZoneName: "shortOffset"
    });

    const refreshParisClock = () => {
      if (!timeNode || !dateNode || !zoneNode) return;
      const now = new Date();
      timeNode.textContent = timeFormatter.format(now);
      timeNode.dateTime = now.toISOString();
      dateNode.textContent = dateFormatter
        .format(now)
        .replace(",", "")
        .toLocaleUpperCase(localeTag);
      const zonePart = zoneFormatter
        .formatToParts(now)
        .find(part => part.type === "timeZoneName");
      if (zonePart) {
        zoneNode.textContent = zonePart.value
          .replace("UTC+", "UTC+")
          .replace("UTC−", "UTC-")
          .replace("GMT+", "UTC+")
          .replace("GMT-", "UTC-")
          .replace("GMT", "UTC");
      }
    };

    refreshParisClock();
    window.setInterval(refreshParisClock, 1000);

    toggle.addEventListener("click", () => {
      expanded = !expanded;
      renderHudState();
    });

    if (emailToggle && contactPopover) {
      emailToggle.addEventListener("click", event => {
        event.stopPropagation();
        const open = emailToggle.getAttribute("aria-expanded") === "true";
        closeInfo();
        setContactOpen(!open);
      });
      contactPopover.addEventListener("click", event => event.stopPropagation());
    }

    if (contactCopy) {
      contactCopy.addEventListener("click", async () => {
        const address = "contact@france2027.app";
        try {
          if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(address);
          } else {
            const field = document.createElement("textarea");
            field.value = address;
            field.setAttribute("readonly", "");
            field.style.position = "fixed";
            field.style.opacity = "0";
            document.body.append(field);
            field.select();
            document.execCommand("copy");
            field.remove();
          }
          contactCopy.textContent = shellText("COPIÉE", "COPIED");
          window.setTimeout(() => { contactCopy.textContent = shellText("COPIER L’ADRESSE", "COPY ADDRESS"); }, 1600);
        } catch (_) {
          contactCopy.textContent = shellText("ÉCHEC DE LA COPIE", "COPY FAILED");
          window.setTimeout(() => { contactCopy.textContent = shellText("COPIER L’ADRESSE", "COPY ADDRESS"); }, 1600);
        }
      });
    }

    if (infoToggle && infoPopover) {
      infoToggle.addEventListener("click", event => {
        event.stopPropagation();
        const open = infoToggle.getAttribute("aria-expanded") === "true";
        closeContact();
        setInfoOpen(!open);
      });
      infoPopover.addEventListener("click", event => event.stopPropagation());
    }

    document.addEventListener("click", () => {
      closeContact();
      closeInfo();
    });

    window.addEventListener("keydown", event => {
      if (event.key !== "Escape") return;
      if (emailToggle?.getAttribute("aria-expanded") === "true") {
        closeContact();
        emailToggle.focus({ preventScroll: true });
        return;
      }
      if (infoToggle?.getAttribute("aria-expanded") === "true") {
        closeInfo();
        infoToggle.focus({ preventScroll: true });
        return;
      }
      if (expanded) {
        expanded = false;
        renderHudState();
        toggle.focus({ preventScroll: true });
      }
    });

    renderHudState();
    syncHudGeometry();
    window.addEventListener("resize", syncHudGeometry, { passive: true });
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(syncHudGeometry);
      observer.observe(shell);
    }
  };

  const initStandaloneShell = () => {
    initClocks();
    initApplicationHud();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initStandaloneShell, { once: true });
  } else {
    initStandaloneShell();
  }
})();
/* === END FR27 STANDALONE SHELL === */
