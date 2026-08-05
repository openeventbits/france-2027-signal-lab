(() => {
  "use strict";


  const translate = (key, fallback) => {
    const localizer = globalThis.FR27I18N;

    return localizer && typeof localizer.t === "function"
      ? localizer.t(key)
      : fallback;
  };

  const mount = document.getElementById("hybrid-signal-board");
  const topMediaMount = document.getElementById(
    "top-media-pulse-content"
  );
  const topMediaMetrics = document.getElementById(
    "top-media-pulse-metrics"
  );

  if (!mount) return;

  const views = Object.freeze({
    runoff: {
      label: "RUNOFF",
      title: "Closest Runoff",
      hash: "#signal-runoff",
      tabId: "signal-runoff-tab",
      panelId: "signal-runoff-panel",
      index: "1"
    },
    candidates: {
      label: "CANDIDATES",
      title: "Candidate Signals",
      hash: "#signal-candidates",
      tabId: "signal-candidates-tab",
      panelId: "signal-candidates-panel"
    },
    events: {
      label: "EVENTS",
      title: "Campaign Events",
      hash: "#signal-events",
      tabId: "signal-events-tab",
      panelId: "signal-events-panel"
    },
    agenda: {
      label: "AGENDA",
      title: "Campaign Agenda",
      hash: "#signal-agenda",
      tabId: "signal-agenda-tab",
      panelId: "signal-agenda-panel",
      index: "3"
    },
    claims: {
      label: "CLAIM SCRUTINY",
      title: "Claim Scrutiny",
      hash: "#signal-claims",
      tabId: "signal-claims-tab",
      panelId: "signal-claims-panel",
      index: "4"
    },
    pollCompare: {
      label: translate("signal_board.poll_compare", "POLL COMPARE"),
      title: "Polling Evidence",
      hash: "#signal-poll-compare",
      tabId: "signal-poll-compare-tab",
      panelId: "polling-evidence-lab"
    }
  });
  const viewOrder = Object.keys(views);
  const hashToView = new Map(viewOrder.map(key => [views[key].hash, key]));
  const defaultView = "candidates";
  const state = {
    activeView: hashToView.get(window.location.hash) || defaultView,
    selectedRunoffHistoryKey: "",
    selectedAgendaTopicId: "",
    claimsRelationship: "all",
    claimsCandidateId: "",
    claimsPublisher: "",
    selectedCandidateSignalsId: null,
    candidateSignals: {
      status: "loading",
      candidates: [],
      metadata: {},
      reason: null
    },
    scrollOnNextHash: false
  };
  const runoffArchiveState = {
    status: "loading",
    events: [],
    error: ""
  };
  let runoffArchiveRequest = null;
  const candidateSignalsRequest =
    window.France2027CandidateSignals
      ?.load("candidate_signals.json")
      .then(candidateSignalsState => {
        state.candidateSignals = candidateSignalsState;
        document
          .getElementById("candidate-signals-root")
          ?.setAttribute(
            "data-candidate-signals-state",
            candidateSignalsState.status
          );
        renderAll();
        return candidateSignalsState;
      })
      .catch(() => {
        const candidateSignalsState = {
          status: "unavailable",
          candidates: [],
          metadata: {},
          reason: "fetch_failed"
        };
        state.candidateSignals = candidateSignalsState;
        document
          .getElementById("candidate-signals-root")
          ?.setAttribute(
            "data-candidate-signals-state",
            candidateSignalsState.status
          );
        renderAll();
        return candidateSignalsState;
      });

  const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const percent = value => Number.isFinite(value) ? formatScore(value) : "—";
  const countLabel = (value, singular, plural = singular + "s") => `${value} ${value === 1 ? singular : plural}`;
  const formatDay = value => formatDate(String(value).slice(0, 10));
  const statusCopy = status => ({
    agree: "Agree",
    split: "Pollsters split",
    ambiguous: "No single closest matchup",
    insufficient: "Insufficient comparable evidence",
    unavailable: "Unavailable"
  })[status] || "Unavailable";

  function isValidRunoffArchivePayload(payload) {
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.events)) return false;
    const eventIds = new Set();
    return payload.events.every(event => {
      if (!event || typeof event !== "object" || typeof event.event_id !== "string" || !event.event_id) return false;
      if (eventIds.has(event.event_id)) return false;
      eventIds.add(event.event_id);
      return typeof event.matchup_key === "string" && Boolean(event.matchup_key) &&
        typeof event.pollster === "string" && Boolean(event.pollster) &&
        /^\d{4}-\d{2}-\d{2}$/.test(event.fieldwork_start) &&
        /^\d{4}-\d{2}-\d{2}$/.test(event.fieldwork_end) &&
        Array.isArray(event.candidates) && event.candidates.length === 2 &&
        event.candidates.every(candidate => candidate && typeof candidate.name === "string" && Number.isFinite(candidate.score)) &&
        Number.isFinite(event.margin);
    });
  }

  function loadRunoffArchive(fetchImplementation = typeof window.fetch === "function" ? window.fetch.bind(window) : null) {
    if (runoffArchiveRequest || !fetchImplementation) return runoffArchiveRequest;
    runoffArchiveRequest = fetchImplementation("second_round_polls.json", { cache: "no-store" })
      .then(response => {
        if (!response.ok) throw new Error(`second_round_polls.json returned HTTP ${response.status}`);
        return response.json();
      })
      .then(payload => {
        if (!isValidRunoffArchivePayload(payload)) throw new Error("Invalid second_round_polls.json payload");
        runoffArchiveState.status = "ready";
        runoffArchiveState.events = payload.events.slice();
        runoffArchiveState.error = "";
        if (typeof mount.querySelectorAll === "function") renderAll();
        return runoffArchiveState;
      })
      .catch(error => {
        runoffArchiveState.status = "unavailable";
        runoffArchiveState.events = [];
        runoffArchiveState.error = error instanceof Error ? error.message : "Archive enrichment unavailable";
        console.warn("Runoff archive enrichment unavailable.", error);
        if (typeof mount.querySelectorAll === "function") renderAll();
        return runoffArchiveState;
      });
    return runoffArchiveRequest;
  }
  function viewModelState(name) {
    const loadState = dashboardState.loadState[name];
    if (loadState === "loading") return { state: "loading", message: "Loading repository data…" };
    if (loadState === "error") return { state: "unavailable", message: "This data domain is unavailable. Other signals remain live." };
    if (!dashboardState[name]) return { state: "empty", message: "No supported data is available." };
    return null;
  }

  function initials(name) {
    return String(name || "")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(part => part[0])
      .join("")
      .toUpperCase();
  }

  function portraitMarkup(name, eager = false) {
    const portrait = candidatePortraits[name];
    const fallback = escapeHtml(initials(name));
    if (!portrait) return `<span class="hybrid-portrait" aria-hidden="true">${fallback}</span>`;
    return `<span class="hybrid-portrait">
      <span aria-hidden="true">${fallback}</span>
      <img src="${escapeAttribute(portrait)}" alt="AI-generated portrait of ${escapeAttribute(name)}"
           loading="${eager ? "eager" : "lazy"}" decoding="async" onerror="this.remove()">
    </span>`;
  }

  function exactRunoffWindowLabel(event) {
    return formatRunoffFieldwork({ start: event.fieldwork_start, end: event.fieldwork_end });
  }

  function runoffScoresForCandidates(observation, candidates) {
    return candidates.map(name => observation.candidates.find(candidate => candidate.name === name)?.score);
  }

  function enrichRunoffResult(result, eventById) {
    const raw = typeof result.event_id === "string" ? eventById.get(result.event_id) : null;
    return {
      ...result,
      fieldwork_start: raw?.fieldwork_start || result.fieldwork_start || "",
      fieldwork_end: raw?.fieldwork_end || result.fieldwork_end || "",
      sampleSize: raw && Number.isInteger(raw.sample_size) ? raw.sample_size : null,
      archiveMatched: Boolean(raw)
    };
  }

  function buildRunoffArchiveModel(archiveState, currentCommonKeys, preferredHistoryKey) {
    if (archiveState.status !== "ready") {
      return {
        state: archiveState.status === "loading" ? "loading" : "unavailable",
        message: archiveState.status === "loading"
          ? "Loading the source-linked archive…"
          : "Archive coverage and history are locally unavailable; current comparison evidence remains available.",
        eventById: new Map(),
        footprint: null,
        matchups: [],
        selectedHistoryKey: "",
        history: [],
        otherMatchups: []
      };
    }

    const events = archiveState.events;
    const eventById = new Map(events.map(event => [event.event_id, event]));
    const matchupMap = new Map();
    events.forEach(event => {
      if (!matchupMap.has(event.matchup_key)) {
        matchupMap.set(event.matchup_key, {
          key: event.matchup_key,
          candidates: event.candidates.map(candidate => candidate.name),
          observations: []
        });
      }
      matchupMap.get(event.matchup_key).observations.push(event);
    });
    const matchups = [...matchupMap.values()].sort((a, b) =>
      a.candidates.join(" vs ").localeCompare(b.candidates.join(" vs "), "fr")
    );
    matchups.forEach(matchup => {
      matchup.observations = matchup.observations.slice().sort((a, b) =>
        String(a.fieldwork_end).localeCompare(String(b.fieldwork_end)) ||
        String(a.fieldwork_start).localeCompare(String(b.fieldwork_start)) ||
        String(a.pollster).localeCompare(String(b.pollster), "fr") ||
        String(a.event_id).localeCompare(String(b.event_id))
      );
    });
    const selectedHistoryKey = matchupMap.has(preferredHistoryKey)
      ? preferredHistoryKey
      : matchups[0]?.key || "";
    const selectedHistory = matchupMap.get(selectedHistoryKey);
    const windows = new Map();
    events.forEach(event => windows.set(`${event.fieldwork_start}/${event.fieldwork_end}`, event));
    const sortedWindows = [...windows.values()].sort((a, b) =>
      String(a.fieldwork_end).localeCompare(String(b.fieldwork_end)) ||
      String(a.fieldwork_start).localeCompare(String(b.fieldwork_start))
    );
    const commonKeys = new Set(currentCommonKeys);
    return {
      state: "ready",
      message: "",
      eventById,
      footprint: {
        observationCount: events.length,
        matchupCount: matchupMap.size,
        pollsterCount: new Set(events.map(event => event.pollster)).size,
        windowCount: windows.size,
        earliestWindow: sortedWindows[0] || null,
        latestWindow: sortedWindows[sortedWindows.length - 1] || null
      },
      matchups,
      selectedHistoryKey,
      history: selectedHistory?.observations || [],
      otherMatchups: matchups
        .filter(matchup => !commonKeys.has(matchup.key))
        .map(matchup => ({
          ...matchup,
          latest: matchup.observations[matchup.observations.length - 1]
        }))
    };
  }

  function buildRunoffViewModel(archiveState = runoffArchiveState) {
    const unavailable = viewModelState("runoff");
    if (unavailable) return { domain: "runoff", ...unavailable };

    const payload = dashboardState.runoff;
    if (!payload || !["agree", "split", "ambiguous", "insufficient"].includes(payload.status)) {
      return { domain: "runoff", state: "invalid", message: "Runoff evidence is unavailable because the derived artifact is malformed." };
    }
    const commonMatchups = Array.isArray(payload.common_matchups) ? payload.common_matchups : [];
    const preferredHistoryKey = state.selectedRunoffHistoryKey || payload.selected_matchup?.matchup_key || commonMatchups[0]?.matchup_key || "";
    const archive = buildRunoffArchiveModel(archiveState, commonMatchups.map(matchup => matchup.matchup_key), preferredHistoryKey);
    const model = {
      domain: "runoff",
      state: payload.status === "insufficient" ? "empty" : "ready",
      status: payload.status,
      statusLabel: statusCopy(payload.status),
      message: payload.message,
      disclosure: payload.disclosure,
      fieldworkWindow: payload.fieldwork_window || null,
      fieldworkLabel: payload.fieldwork_window ? formatRunoffFieldwork(payload.fieldwork_window) : "Fieldwork unavailable",
      pollsterCount: number(payload.pollster_count),
      commonMatchupCount: number(payload.common_matchup_count),
      selectedMatchup: null,
      featuredObservation: null,
      commonMatchups: commonMatchups.map(matchup => ({
        ...matchup,
        results: Array.isArray(matchup.results) ? matchup.results.map(result => enrichRunoffResult(result, archive.eventById)) : []
      })),
      pollsters: Array.isArray(payload.pollsters)
        ? payload.pollsters.map(pollster => ({
          ...pollster,
          closest_matchups: Array.isArray(pollster.closest_matchups)
            ? pollster.closest_matchups.map(matchup => ({ ...matchup, result: enrichRunoffResult(matchup.result, archive.eventById) }))
            : []
        }))
        : [],
      archive
    };

    if (payload.status !== "agree" || !payload.selected_matchup) return model;

    const selected = payload.selected_matchup;
    const observations = selected.results.map((result, sourceIndex) => ({
      ...enrichRunoffResult(result, archive.eventById),
      sourceIndex,
      observationDate: result.fieldwork_end || result.publication_date || payload.fieldwork_window?.end || ""
    }));
    const featured = [...observations].sort((a, b) =>
      number(a.margin) - number(b.margin) ||
      String(b.observationDate).localeCompare(String(a.observationDate)) ||
      a.sourceIndex - b.sourceIndex
    )[0] || null;

    model.selectedMatchup = {
      key: selected.matchup_key,
      candidates: selected.candidates,
      observations,
      observationCount: observations.length,
      sourceCount: observations.filter(item => safeSourceUrl(item.source_url)).length
    };
    model.featuredObservation = featured;
    return model;
  }
  function utcDateKey(date) {
    return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
  }

  function dateKeyWithOffset(anchor, offset) {
    const date = new Date(anchor);
    date.setUTCDate(date.getUTCDate() + offset);
    return utcDateKey(date);
  }

  function takeMediaLeadersWithTies(
    items,
    nominalLimit,
    valueSelector
  ) {
    if (!items.length || nominalLimit < 1) return [];

    const limit = Math.min(
      nominalLimit,
      items.length
    );

    const cutoff = valueSelector(
      items[limit - 1]
    );

    return items.filter(
      (item, index) =>
        index < limit ||
        Math.abs(
          valueSelector(item) - cutoff
        ) < 0.000001
    );
  }

  function formatMediaShare(value) {
    return Number(value)
      .toFixed(1)
      .replace(/\.0$/, "");
  }

  function formatMediaPeriodRange(startKey, endKey) {
    const parseKey = value => {
      const text = String(value || "");
      const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
      if (!match) return null;

      const date = new Date(Date.UTC(
        Number(match[1]),
        Number(match[2]) - 1,
        Number(match[3])
      ));

      return utcDateKey(date) === text
        ? date
        : null;
    };

    const start = parseKey(startKey);
    const end = parseKey(endKey);

    if (!start || !end || start > end) {
      return "DATE UNAVAILABLE";
    }

    const months = [
      "JAN", "FEB", "MAR", "APR",
      "MAY", "JUN", "JUL", "AUG",
      "SEP", "OCT", "NOV", "DEC"
    ];

    const startDay = start.getUTCDate();
    const endDay = end.getUTCDate();
    const startMonth = months[start.getUTCMonth()];
    const endMonth = months[end.getUTCMonth()];
    const startYear = start.getUTCFullYear();
    const endYear = end.getUTCFullYear();

    if (start.getTime() === end.getTime()) {
      return `${startDay} ${startMonth}`;
    }

    if (
      startYear === endYear &&
      start.getUTCMonth() === end.getUTCMonth()
    ) {
      return `${startDay}–${endDay} ${endMonth}`;
    }

    if (startYear === endYear) {
      return `${startDay} ${startMonth}–${endDay} ${endMonth}`;
    }

    return `${startDay} ${startMonth} ${startYear}–${endDay} ${endMonth} ${endYear}`;
  }

  function isGeneralAgendaTopic(topic) {
    const identity = String(
      topic?.id || topic?.label || ""
    )
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();

    return (
      identity.startsWith("other ") ||
      identity.startsWith("other_") ||
      identity.includes("other campaign coverage")
    );
  }


  function normalizeMediaCandidateLabel(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  function buildMediaCandidateCanonicalizer(items) {
    const preferredByKey = new Map();

    items.forEach(item => {
      const labels = Array.isArray(item?.candidates)
        ? item.candidates
        : [];

      labels.forEach(value => {
        const label = String(value || "").trim();
        const key = normalizeMediaCandidateLabel(label);
        if (!key) return;

        const previous = preferredByKey.get(key) || "";
        if (!previous || label.length > previous.length) {
          preferredByKey.set(key, label);
        }
      });
    });

    const fullCandidates = [...preferredByKey.entries()]
      .filter(([key]) => key.split(" ").length > 1)
      .map(([key, label]) => ({ key, label }));

    const aliases = new Map();

    preferredByKey.forEach((label, key) => {
      const rawTokens = key.split(" ");
      const suffixMatches = fullCandidates.filter(candidate => {
        const fullTokens = candidate.key.split(" ");
        if (fullTokens.length <= rawTokens.length) return false;

        return fullTokens
          .slice(-rawTokens.length)
          .join(" ") === key;
      });

      aliases.set(
        key,
        suffixMatches.length === 1
          ? suffixMatches[0].label
          : label
      );
    });

    return value => {
      const label = String(value || "").trim();
      const key = normalizeMediaCandidateLabel(label);
      return aliases.get(key) || label;
    };
  }

  const MEDIA_CANDIDATE_VISIBILITY_METHOD =
    "share_of_candidate_linked_records";

  const MEDIA_CANDIDATE_VISIBILITY_THRESHOLDS =
    Object.freeze({
      minimum_period_records: 10,
      minimum_period_publishers: 5,
      minimum_common_publishers: 5,
      minimum_publisher_overlap_ratio: 0.5,
      maximum_record_count_ratio: 2.0
    });

  const roundMediaComparisonRatio = value =>
    Math.floor(value * 1000 + 0.5) / 1000;

  const mediaComparisonDateKey = value => {
    const parsed = new Date(String(value || ""));
    return Number.isFinite(parsed.getTime())
      ? utcDateKey(parsed)
      : "";
  };

  const mediaCandidateComparisonGate = quality => {
    const thresholds = MEDIA_CANDIDATE_VISIBILITY_THRESHOLDS;

    if (
      quality.current_record_count <
        thresholds.minimum_period_records ||
      quality.prior_record_count <
        thresholds.minimum_period_records ||
      quality.current_publisher_count <
        thresholds.minimum_period_publishers ||
      quality.prior_publisher_count <
        thresholds.minimum_period_publishers ||
      quality.common_publisher_count <
        thresholds.minimum_common_publishers
    ) {
      return {
        status: "not_comparable",
        reason: "insufficient_data"
      };
    }

    if (
      quality.publisher_overlap_ratio <
        thresholds.minimum_publisher_overlap_ratio ||
      quality.record_count_ratio === null ||
      quality.record_count_ratio >
        thresholds.maximum_record_count_ratio
    ) {
      return {
        status: "not_comparable",
        reason: "publisher_panel_changed"
      };
    }

    return {
      status: "comparable",
      reason: "comparable"
    };
  };

  function deriveCandidateVisibility(payload) {
    const candidateWatch = Array.isArray(payload?.candidate_watch)
      ? payload.candidate_watch
      : [];
    const generatedKey = mediaComparisonDateKey(
      payload?.generated_at
    );
    const candidateKeys = candidateWatch
      .map(item => mediaComparisonDateKey(item?.published_at))
      .filter(Boolean)
      .sort();
    const anchorKey = generatedKey ||
      candidateKeys[candidateKeys.length - 1] ||
      "1970-01-01";
    const anchor = new Date(`${anchorKey}T00:00:00Z`);
    const currentStartKey = dateKeyWithOffset(anchor, -6);
    const currentEndKey = utcDateKey(anchor);
    const priorStartKey = dateKeyWithOffset(anchor, -13);
    const priorEndKey = dateKeyWithOffset(anchor, -7);

    const buildPeriod = (startDate, endDate) => {
      const records = candidateWatch.filter(item => {
        const key = mediaComparisonDateKey(item?.published_at);
        return key >= startDate && key <= endDate;
      });
      const publisherNames = [...new Set(
        records
          .map(item => String(item?.publisher || "").trim())
          .filter(Boolean)
      )].sort();

      return {
        start_date: startDate,
        end_date: endDate,
        record_count: records.length,
        publisher_count: publisherNames.length,
        publisher_names: publisherNames
      };
    };

    const currentPeriod = buildPeriod(
      currentStartKey,
      currentEndKey
    );
    const priorPeriod = buildPeriod(
      priorStartKey,
      priorEndKey
    );
    const currentPublishers = new Set(
      currentPeriod.publisher_names
    );
    const priorPublishers = new Set(
      priorPeriod.publisher_names
    );
    const commonPublisherCount = [
      ...currentPublishers
    ].filter(name => priorPublishers.has(name)).length;
    const publisherUnionCount = new Set([
      ...currentPublishers,
      ...priorPublishers
    ]).size;
    const publisherOverlapRatio =
      roundMediaComparisonRatio(
        publisherUnionCount
          ? commonPublisherCount / publisherUnionCount
          : 0
      );
    const currentRecordCount = currentPeriod.record_count;
    const priorRecordCount = priorPeriod.record_count;
    const recordCountRatio =
      currentRecordCount && priorRecordCount
        ? roundMediaComparisonRatio(
            Math.max(currentRecordCount, priorRecordCount) /
            Math.min(currentRecordCount, priorRecordCount)
          )
        : null;
    const qualityCounts = {
      current_record_count: currentRecordCount,
      prior_record_count: priorRecordCount,
      current_publisher_count: currentPeriod.publisher_count,
      prior_publisher_count: priorPeriod.publisher_count,
      common_publisher_count: commonPublisherCount,
      publisher_union_count: publisherUnionCount,
      publisher_overlap_ratio: publisherOverlapRatio,
      record_count_ratio: recordCountRatio
    };
    const gate = mediaCandidateComparisonGate(qualityCounts);

    return {
      method: MEDIA_CANDIDATE_VISIBILITY_METHOD,
      current_period: currentPeriod,
      prior_period: priorPeriod,
      comparison_quality: {
        ...gate,
        ...qualityCounts,
        thresholds: {
          ...MEDIA_CANDIDATE_VISIBILITY_THRESHOLDS
        }
      }
    };
  }

  function isValidCandidateVisibility(candidateVisibility, payload) {
    if (!candidateVisibility || typeof candidateVisibility !== "object") {
      return false;
    }

    const exactKeys = (value, keys) =>
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).sort().join("|") ===
        [...keys].sort().join("|");
    const periodKeys = [
      "start_date",
      "end_date",
      "record_count",
      "publisher_count",
      "publisher_names"
    ];
    const qualityKeys = [
      "status",
      "reason",
      "current_record_count",
      "prior_record_count",
      "current_publisher_count",
      "prior_publisher_count",
      "common_publisher_count",
      "publisher_union_count",
      "publisher_overlap_ratio",
      "record_count_ratio",
      "thresholds"
    ];
    const expected = deriveCandidateVisibility(payload);

    if (
      !exactKeys(candidateVisibility, [
        "method",
        "current_period",
        "prior_period",
        "comparison_quality"
      ]) ||
      candidateVisibility.method !==
        MEDIA_CANDIDATE_VISIBILITY_METHOD ||
      !exactKeys(candidateVisibility.current_period, periodKeys) ||
      !exactKeys(candidateVisibility.prior_period, periodKeys) ||
      !exactKeys(candidateVisibility.comparison_quality, qualityKeys) ||
      !exactKeys(
        candidateVisibility.comparison_quality.thresholds,
        Object.keys(MEDIA_CANDIDATE_VISIBILITY_THRESHOLDS)
      )
    ) {
      return false;
    }

    const periodsValid = [
      "current_period",
      "prior_period"
    ].every(periodName => {
      const period = candidateVisibility[periodName];
      return (
        /^\d{4}-\d{2}-\d{2}$/.test(period.start_date) &&
        /^\d{4}-\d{2}-\d{2}$/.test(period.end_date) &&
        mediaComparisonDateKey(period.start_date) ===
          period.start_date &&
        mediaComparisonDateKey(period.end_date) ===
          period.end_date &&
        Number.isInteger(period.record_count) &&
        period.record_count >= 0 &&
        Number.isInteger(period.publisher_count) &&
        period.publisher_count >= 0 &&
        Array.isArray(period.publisher_names) &&
        period.publisher_names.every(
          name => typeof name === "string" &&
            name.trim() &&
            name === name.trim()
        ) &&
        period.publisher_names.join("|") ===
          [...new Set(period.publisher_names)].sort().join("|") &&
        period.publisher_count === period.publisher_names.length
      );
    });
    if (!periodsValid) return false;

    const quality = candidateVisibility.comparison_quality;
    const countFields = qualityKeys.filter(key =>
      key.endsWith("_count")
    );
    const ratiosValid =
      typeof quality.publisher_overlap_ratio === "number" &&
      Number.isFinite(quality.publisher_overlap_ratio) &&
      quality.publisher_overlap_ratio >= 0 &&
      quality.publisher_overlap_ratio <= 1 &&
      (
        quality.record_count_ratio === null ||
        (
          typeof quality.record_count_ratio === "number" &&
          Number.isFinite(quality.record_count_ratio) &&
          quality.record_count_ratio >= 1
        )
      );
    if (
      countFields.some(
        key => !Number.isInteger(quality[key]) || quality[key] < 0
      ) ||
      !ratiosValid
    ) {
      return false;
    }

    const equalValues = (left, right) => {
      if (Array.isArray(left) || Array.isArray(right)) {
        return (
          Array.isArray(left) &&
          Array.isArray(right) &&
          left.length === right.length &&
          left.every((value, index) =>
            equalValues(value, right[index])
          )
        );
      }
      if (
        left && right &&
        typeof left === "object" &&
        typeof right === "object"
      ) {
        const leftKeys = Object.keys(left).sort();
        const rightKeys = Object.keys(right).sort();
        return (
          leftKeys.join("|") === rightKeys.join("|") &&
          leftKeys.every(key => equalValues(left[key], right[key]))
        );
      }
      return Object.is(left, right);
    };

    return equalValues(candidateVisibility, expected);
  }

  function resolveCandidateVisibility(payload) {
    return isValidCandidateVisibility(
      payload?.candidate_visibility,
      payload
    )
      ? payload.candidate_visibility
      : deriveCandidateVisibility(payload);
  }

  function buildMediaViewModel() {
    const unavailable = viewModelState("news");
    if (unavailable) {
      return {
        domain: "media",
        ...unavailable
      };
    }

    const payload = dashboardState.news;

    const electionItems = Array.isArray(
      payload.election_news
    )
      ? payload.election_news
      : [];

    const coverageItems = Array.isArray(
      payload.candidate_watch
    )
      ? payload.candidate_watch
      : [];

    const activeFieldVisibility =
      state.candidateSignals.status === "ready"
        ? state.candidateSignals.metadata?.activeFieldVisibility || null
        : null;
    const activePrimary = activeFieldVisibility?.primary || null;
    const comparisonQuality = activePrimary?.comparison_quality || {
      status: "unavailable",
      reason: "active_field_visibility_unavailable"
    };
    const changeAvailable = comparisonQuality.status === "comparable";

    const feedItems = newestNewsItems(
      electionItems
    ).slice(0, 50);

    const generatedKey = String(
      payload.generated_at || ""
    ).slice(0, 10);

    const anchor =
      /^\d{4}-\d{2}-\d{2}$/.test(
        generatedKey
      )
        ? new Date(
            `${generatedKey}T00:00:00Z`
          )
        : new Date(
            Math.max(
              ...electionItems.map(
                item =>
                  new Date(
                    item.published_at
                  ).getTime()
              )
            )
          );

    const safeAnchor = Number.isFinite(
      anchor.getTime()
    )
      ? anchor
      : new Date();

    const activityCounts = new Map();

    electionItems.forEach(item => {
      const key = String(
        item.published_at || ""
      ).slice(0, 10);

      activityCounts.set(
        key,
        (activityCounts.get(key) || 0) + 1
      );
    });

    const dailyActivity = [];

    for (
      let offset = 13;
      offset >= 0;
      offset -= 1
    ) {
      const date = new Date(safeAnchor);
      date.setUTCDate(
        date.getUTCDate() - offset
      );

      const key = utcDateKey(date);

      dailyActivity.push({
        key,
        date,
        count:
          activityCounts.get(key) || 0
      });
    }

    const latestStartKey = activePrimary?.current_period?.start_date || "";
    const latestEndKey = activePrimary?.current_period?.end_date || "";
    const previousStartKey = activePrimary?.prior_period?.start_date || "";
    const previousEndKey = activePrimary?.prior_period?.end_date || "";
    const latestDenominator = activePrimary?.current_period?.record_count ?? null;
    const previousDenominator = activePrimary?.prior_period?.record_count ?? null;
    const candidateCoverageAvailable = Boolean(activePrimary);
    const activeRows = activePrimary
      ? [
          ...activePrimary.main.map(row => ({ ...row, tier: "main" })),
          ...activePrimary.secondary.map(row => ({ ...row, tier: "secondary" }))
        ]
      : [];
    const compareNullableDescending = (left, right, field) => {
      const leftMissing = left[field] === null;
      const rightMissing = right[field] === null;
      if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
      return leftMissing ? 0 : right[field] - left[field];
    };
    const candidateCoverageShares = activeRows
      .map(row => {
        const latestShare = row.current_share === null
          ? null
          : row.current_share * 100;
        const previousShare = row.prior_share === null
          ? null
          : row.prior_share * 100;
        const delta = changeAvailable && row.share_change !== null
          ? row.share_change * 100
          : null;
        return {
          id: row.candidate_id,
          name: row.candidate_name,
          status: row.status,
          tier: row.tier,
          tierLabel: row.tier.toUpperCase(),
          latestCount: row.current_record_count,
          previousCount: row.prior_record_count,
          latestShare,
          previousShare,
          changeAvailable: delta !== null,
          delta,
          changePp: delta,
          direction: delta === null
            ? "unavailable"
            : delta > 0.05
              ? "positive"
              : delta < -0.05
                ? "negative"
                : "flat",
          latestItems: [],
          previousItems: []
        };
      })
      .sort((left, right) => {
        const metricOrder =
          compareNullableDescending(left, right, "latestShare") ||
          right.latestCount - left.latestCount ||
          compareNullableDescending(left, right, "previousShare") ||
          right.previousCount - left.previousCount;
        if (metricOrder) return metricOrder;
        const leftName = left.name.toLowerCase();
        const rightName = right.name.toLowerCase();
        if (leftName !== rightName) return leftName < rightName ? -1 : 1;
        return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
      });
    const candidateCoverageLeaders = candidateCoverageShares.slice(0, 6);

    const publisherCounts =
      electionItems.reduce(
        (counts, item) => {
          const publisher = String(
            item.publisher || ""
          ).trim();

          if (!publisher) return counts;

          counts.set(
            publisher,
            (counts.get(publisher) || 0) + 1
          );

          return counts;
        },
        new Map()
      );

    const publisherCount =
      publisherCounts.size;

    const publisherRanking = [
      ...publisherCounts.entries()
    ]
      .map(([name, count]) => ({
        name,
        count
      }))
      .sort(
        (a, b) =>
          b.count - a.count ||
          a.name.localeCompare(
            b.name,
            "fr"
          )
      );

    const topPublishers =
      publisherRanking.slice(0, 5);

    const agendaTopics =
      Array.isArray(
        payload.campaign_agenda
          ?.topics
      )
        ? payload.campaign_agenda
            .topics
            .filter(
              topic =>
                topic.display_eligible
            )
        : [];

    const specificAgendaTopics =
      agendaTopics
        .filter(
          topic =>
            !isGeneralAgendaTopic(
              topic
            )
        )
        .sort(
          (a, b) =>
            number(
              b.source_day_count
            ) -
              number(
                a.source_day_count
              ) ||
            number(
              b.publisher_count
            ) -
              number(
                a.publisher_count
              ) ||
            String(
              a.label
            ).localeCompare(
              String(
                b.label
              ),
              "en"
            )
        );

    const mediaMetricOrNull = value => {
      if (
        value === null ||
        value === undefined ||
        String(value).trim() === ""
      ) {
        return null;
      }

      const metric = Number(value);

      return Number.isFinite(metric)
        ? metric
        : null;
    };

    const topicCoverage =
      specificAgendaTopics
        .slice(0, 5)
        .map(topic => ({
          id: String(
            topic.id || ""
          ),
          label: String(
            topic.label || ""
          ),
          sourceDays:
            mediaMetricOrNull(
              topic.source_day_count
            ),
          itemCount:
            mediaMetricOrNull(
              topic.item_count
            ),
          publishers:
            mediaMetricOrNull(
              topic.publisher_count
            )
        }));

    const windowDays = number(
      payload.window_days
    );

    const activityWindowDays =
      dailyActivity.length;

    const activityItemCount =
      dailyActivity.reduce(
        (sum, day) =>
          sum + day.count,
        0
      );

    return {
      domain: "media",
      state:
        feedItems.length
          ? "ready"
          : "empty",
      windowDays,
      activityWindowDays,
      activityItemCount,
      electionNewsCount:
        number(
          payload.counts
            ?.election_news
        ),
      candidateWatchCount:
        coverageItems.length,
      acceptedNewsPublisherCount:
        publisherCount,
      topPublishers,
      publisherRanking,
      dailyActivity,
      activityMax: Math.max(
        1,
        ...dailyActivity.map(
          day => day.count
        )
      ),
      feedItems,
      candidateCoverageAvailable,
      activeFieldVisibility,
      candidateCoverage:
        candidateCoverageShares,
      candidateCoverageLeaders,
      comparisonQuality,
      latestCandidateArticleCount:
        latestDenominator,
      previousCandidateArticleCount:
        previousDenominator,
      latestStartKey,
      latestEndKey,
      previousStartKey,
      previousEndKey,
      latestPeriodLabel:
        formatMediaPeriodRange(
          latestStartKey,
          latestEndKey
        ),
      priorPeriodLabel:
        formatMediaPeriodRange(
          previousStartKey,
          previousEndKey
        ),
      topicCoverage,
      latestAcceptedAt:
        feedItems[0]
          ?.published_at || "",
      generatedAt:
        payload.generated_at
    };
  }
  function buildAgendaViewModel() {
    const unavailable = viewModelState("news");
    if (unavailable) return { domain: "agenda", ...unavailable };

    const agenda = dashboardState.news.campaign_agenda;
    const allTopics = Array.isArray(agenda?.topics) ? agenda.topics : [];
    const sorted = [...allTopics].sort((a, b) =>
      number(b.source_day_count) - number(a.source_day_count) ||
      number(b.item_count) - number(a.item_count) ||
      a.label.localeCompare(b.label, "en")
    );
    const eligible = sorted.filter(topic => topic.display_eligible);
    const selectable = eligible.length ? eligible : sorted;
    if (!selectable.some(topic => topic.id === state.selectedAgendaTopicId)) {
      state.selectedAgendaTopicId = selectable[0]?.id || "";
    }
    const selectedTopic = selectable.find(topic => topic.id === state.selectedAgendaTopicId) || selectable[0] || null;
    return {
      domain: "agenda",
      state: selectable.length ? "ready" : "empty",
      topics: selectable,
      eligibleTopics: eligible,
      selectedTopic,
      maxSourceDays: Math.max(1, ...selectable.map(topic => number(topic.source_day_count))),
      displayMinimum: number(agenda?.display_min_source_days),
      inputItemCount: number(agenda?.input_item_count),
      windowDays: number(agenda?.window_days || dashboardState.news.window_days),
      method: agenda?.method || "",
      generatedAt:
        dashboardState.news.generated_at
    };
  }

  function ratingDisplay(review) {
    const fallback = claimRatingDisplay[review.rating] || { label: "Unclassified", tone: "" };
    return {
      label: typeof review.rating_display === "string" && review.rating_display.trim()
        ? review.rating_display.trim()
        : fallback.label,
      family: typeof review.rating_family === "string" && review.rating_family.trim()
        ? review.rating_family.trim()
        : fallback.tone.replace(/^is-/, "") || "unclassified",
      original: review.rating
    };
  }

  function buildClaimsViewModel() {
    const unavailable = viewModelState("claims");
    if (unavailable) return { domain: "claims", ...unavailable };

    const payload = dashboardState.claims;
    const reviews = Array.isArray(payload.reviews) ? payload.reviews : [];
    const candidateMap = new Map();
    const publishers = new Map();
    let byAssociations = 0;
    let aboutAssociations = 0;

    reviews.forEach(review => {
      publishers.set(review.publisher_name, (publishers.get(review.publisher_name) || 0) + 1);
      review.candidate_associations.forEach(association => {
        if (!candidateMap.has(association.candidate_id)) {
          candidateMap.set(association.candidate_id, {
            id: association.candidate_id,
            name: association.candidate_name,
            by: 0,
            about: 0
          });
        }
        const candidate = candidateMap.get(association.candidate_id);
        candidate[association.relationship] += 1;
        if (association.relationship === "by") byAssociations += 1;
        if (association.relationship === "about") aboutAssociations += 1;
      });
    });

    const candidates = [...candidateMap.values()].sort((a, b) =>
      (b.by + b.about) - (a.by + a.about) || a.name.localeCompare(b.name, "fr")
    );
    const publisherNames = [...publishers.keys()].sort((a, b) => a.localeCompare(b, "fr"));
    const totalAssociations = byAssociations + aboutAssociations;
    return {
      domain: "claims",
      state: reviews.length ? "ready" : "empty",
      reviews,
      reviewCount: reviews.length,
      byAssociations,
      aboutAssociations,
      totalAssociations,
      byPercent: totalAssociations ? byAssociations / totalAssociations * 100 : 0,
      aboutPercent: totalAssociations ? aboutAssociations / totalAssociations * 100 : 0,
      candidates,
      coveredCandidateCount: candidates.length,
      publisherNames,
      publisherCount: publisherNames.length,
      latestReviewDate: reviews[0]?.review_date || ""
    };
  }

  function safelyBuildViewModel(domain, builder) {
    try {
      return builder();
    } catch (error) {
      console.warn(`Hybrid ${domain} view model unavailable`, error);
      return { domain, state: "invalid", message: "Some rows could not be validated for this signal." };
    }
  }

  function buildAllViewModels() {
    return {
      runoff: safelyBuildViewModel("runoff", buildRunoffViewModel),
      media: safelyBuildViewModel("media", buildMediaViewModel),
      agenda: safelyBuildViewModel("agenda", buildAgendaViewModel),
      claims: safelyBuildViewModel("claims", buildClaimsViewModel)
    };
  }

  function cardShell(view, kicker, body, description = "") {
    const config = views[view] || { title: "Media Pulse", index: "2" };
    const descriptionId = `hybrid-card-${view}-description`;
    return `<button class="hybrid-card hybrid-card-${view}" type="button"
      data-hybrid-card="${view}" aria-pressed="false" aria-label="${escapeAttribute(config.title)}. Open detail."${description ? ` aria-describedby="${descriptionId}"` : ""}>
      ${description ? `<span class="visually-hidden" id="${descriptionId}">${escapeHtml(description)}</span>` : ""}
      <span class="hybrid-card-head">
        <span class="hybrid-card-index" aria-hidden="true">${config.index}</span>
        <span class="hybrid-card-title">${escapeHtml(config.title)}</span>
      </span>
      <span class="hybrid-card-kicker">${escapeHtml(kicker)}</span>
      <span class="hybrid-card-body">${body}</span>
      <span class="hybrid-card-action">Open detail <span aria-hidden="true">→</span></span>
    </button>`;
  }

  function summaryState(model) {
    const errorClass = model.state === "unavailable" ? " is-error" : "";
    return `<span class="hybrid-state is-compact${errorClass}">${escapeHtml(model.message || "No supported data is available.")}</span>`;
  }

  function renderRunoffSummary(model) {
    if (model.state !== "ready" || !model.selectedMatchup || !model.featuredObservation) {
      return cardShell("runoff", model.statusLabel || "Second-round source evidence", summaryState(model));
    }
    const [leftName, rightName] = model.selectedMatchup.candidates;
    const leftScore = model.featuredObservation.candidates.find(item => item.name === leftName)?.score;
    const rightScore = model.featuredObservation.candidates.find(item => item.name === rightName)?.score;
    return cardShell("runoff", `${model.featuredObservation.pollster} · ${model.fieldworkLabel}`, `
      <span class="hybrid-runoff-summary">
        <span class="hybrid-runoff-person">
          ${portraitMarkup(leftName, true)}
          <span><span class="hybrid-runoff-name">${escapeHtml(leftName)}</span><span class="hybrid-runoff-score">${percent(leftScore)}</span></span>
        </span>
        <span class="hybrid-versus" aria-hidden="true">VS</span>
        <span class="hybrid-runoff-person is-right">
          <span><span class="hybrid-runoff-name">${escapeHtml(rightName)}</span><span class="hybrid-runoff-score">${percent(rightScore)}</span></span>
          ${portraitMarkup(rightName, true)}
        </span>
      </span>
      <span class="hybrid-runoff-margin">Absolute margin <strong>${number(model.featuredObservation.margin)} pts</strong></span>
      <span class="hybrid-summary-meta">
        <span><strong>${model.selectedMatchup.observationCount}</strong> supporting observations</span>
        <span><strong>${model.selectedMatchup.sourceCount}/${model.selectedMatchup.observationCount}</strong> source links available</span>
      </span>`, `${leftName} versus ${rightName}; smallest reported margin ${number(model.featuredObservation.margin)} points; ${model.featuredObservation.pollster}; ${model.selectedMatchup.observationCount} source observations.`);
  }

  function activityBars(days, max, compact = false) {
    const scale = compact ? 40 : 118;
    return days.map(day => {
      const height = day.count ? Math.max(5, day.count / max * scale) : 3;
      return compact
        ? `<span class="hybrid-mini-bar" style="--hybrid-height:${height.toFixed(1)}px" aria-hidden="true"></span>`
        : `<span class="hybrid-activity-day" aria-hidden="true">
            <span class="hybrid-activity-count">${day.count}</span>
            <span class="hybrid-activity-bar" style="--hybrid-height:${height.toFixed(1)}px"></span>
          </span>`;
    }).join("");
  }

  function deriveAcceptedNewsPublisherMetric(value, windowDays) {
    const available =
      Number.isInteger(value) &&
      value >= 0 &&
      Number.isInteger(windowDays) &&
      windowDays > 0;

    if (!available) {
      return {
        valueText: "—",
        secondaryText: "publisher count unavailable",
        accessibleText:
          "Accepted election-news publisher count unavailable"
      };
    }

    return {
      valueText: String(value),
      secondaryText: windowDays + "-day publishers",
      accessibleText:
        value + " distinct " +
        (value === 1 ? "publisher" : "publishers") +
        " represented in accepted election news during the " +
        windowDays + "-day source window"
    };
  }

  function renderMediaSummary(model) {
    if (model.state !== "ready") {
      return cardShell(
        "media",
        "Latest 14 calendar days",
        summaryState(model)
      );
    }

    const contribution = deriveAcceptedNewsPublisherMetric(
      model.acceptedNewsPublisherCount,
      model.windowDays
    );

    return cardShell("media", `14-day activity · ${model.windowDays}-day source scope`, `
      <span class="hybrid-mini-bars" role="img" aria-label="Accepted election-news items by day for the latest 14 calendar days">
        ${activityBars(model.dailyActivity, model.activityMax, true)}
      </span>
      <span class="visually-hidden">${model.dailyActivity.map(day => `${formatDay(day.key)}: ${day.count}`).join("; ")}</span>
      <span class="hybrid-media-stats">
        <span class="hybrid-mini-stat"><strong>${model.activityItemCount}</strong>${model.activityWindowDays}-day activity</span>
        <span class="hybrid-mini-stat"><strong>${model.electionNewsCount}</strong>${model.windowDays}-day news</span>
        <span class="hybrid-mini-stat"><strong>${model.candidateWatchCount}</strong>${model.windowDays}-day watch</span>
        <span class="hybrid-mini-stat"><strong>${escapeHtml(contribution.valueText)}</strong>${escapeHtml(contribution.secondaryText)}</span>
      </span>
      <span class="hybrid-summary-meta" style="margin-top:8px">Latest accepted item: <strong>${model.latestAcceptedAt ? escapeHtml(formatNewsDateTime(model.latestAcceptedAt)) : "Unavailable"}</strong></span>`,
      `${model.activityItemCount} accepted election-news items in the displayed ${model.activityWindowDays}-day activity window; ${model.electionNewsCount} accepted election-news items and ${model.candidateWatchCount} candidate-watch records in the ${model.windowDays}-day source window; ${contribution.accessibleText}.`);
  }

  function renderAgendaSummary(model) {
    if (model.state !== "ready") return cardShell("agenda", "Recurring campaign topics", summaryState(model));
    return cardShell("agenda", `Recurring topics · ${model.windowDays}-day source window`, `
      <span class="hybrid-ranking">
        ${model.eligibleTopics.slice(0, 3).map(topic => `
          <span class="hybrid-topic-summary-row">
            <span>${escapeHtml(topic.label)}</span>
            <span class="hybrid-track" aria-hidden="true"><span class="hybrid-fill" style="--hybrid-width:${(number(topic.source_day_count) / model.maxSourceDays * 100).toFixed(1)}%"></span></span>
            <span class="hybrid-topic-count">${topic.source_day_count} source-days</span>
          </span>
          <span class="hybrid-summary-meta">${countLabel(topic.item_count, "item")} · ${countLabel(topic.publisher_count, "publisher")}</span>
        `).join("")}
      </span>`, `${model.eligibleTopics.length} recurring topics in the ${model.windowDays}-day source window; top topic has ${number(model.eligibleTopics[0]?.source_day_count)} source-days.`);
  }

  function renderClaimsSummary(model) {
    if (model.state !== "ready") return cardShell("claims", "Validated publisher reviews", summaryState(model));
    return cardShell("claims", "Candidate associations in validated reviews", `
      <span class="hybrid-claims-numbers">
        <span class="hybrid-claims-number"><strong>${model.byAssociations}</strong>BY associations</span>
        <span class="hybrid-claims-number"><strong>${model.aboutAssociations}</strong>ABOUT associations</span>
      </span>
      <span class="hybrid-summary-meta"><strong>${model.reviewCount}</strong> validated reviews · <strong>${model.totalAssociations}</strong> total associations · <strong>${model.coveredCandidateCount}</strong> candidates</span>
      <span class="hybrid-relation-strip" role="img" aria-label="${model.byAssociations} BY candidate associations and ${model.aboutAssociations} ABOUT candidate associations">
        <span class="hybrid-relation-by" style="--hybrid-by:${model.byPercent.toFixed(2)}%"></span>
        <span class="hybrid-relation-about" style="--hybrid-about:${model.aboutPercent.toFixed(2)}%"></span>
      </span>
      <span class="hybrid-relation-legend"><span><strong>${model.byPercent.toFixed(0)}%</strong> BY</span><span><strong>${model.aboutPercent.toFixed(0)}%</strong> ABOUT</span></span>
      <span class="hybrid-summary-meta">Latest review: <strong>${model.latestReviewDate ? formatDay(model.latestReviewDate) : "Unavailable"}</strong></span>`,
      `${model.reviewCount} validated reviews; ${model.byAssociations} BY and ${model.aboutAssociations} ABOUT associations, ${model.totalAssociations} candidate associations total; ${model.coveredCandidateCount} distinct candidates covered.`);
  }

  function renderSummaryGrid(models) {
    return `<div class="hybrid-summary-grid">
      ${renderRunoffSummary(models.runoff)}
      ${renderMediaSummary(models.media)}
      ${renderAgendaSummary(models.agenda)}
      ${renderClaimsSummary(models.claims)}
    </div>`;
  }

  function sourceLink(url, label, className = "", accessibleLabel = "") {
    const safe = safeSourceUrl(url);
    return safe
      ? `<a class="${className}" href="${escapeAttribute(safe)}" target="_blank" rel="noopener noreferrer"${accessibleLabel ? ` aria-label="${escapeAttribute(accessibleLabel)}"` : ""}>${escapeHtml(label)} <span aria-hidden="true">↗</span></a>`
      : `<span class="${className}">Source unavailable</span>`;
  }

  function runoffSampleLabel(value) {
    return Number.isInteger(value) ? `n=${new Intl.NumberFormat("en-US").format(value)}` : "n unavailable";
  }

  function runoffScorePair(observation, candidates) {
    const scores = runoffScoresForCandidates(observation, candidates);
    return `${percent(scores[0])} · ${percent(scores[1])}`;
  }

  function runoffMonthYear(event) {
    if (!event?.fieldwork_end) return "Date unavailable";
    return new Intl.DateTimeFormat("en-GB", {
      month: "short",
      year: "numeric",
      timeZone: "UTC"
    }).format(new Date(`${event.fieldwork_end}T00:00:00Z`));
  }
  function runoffTitleCaseDate(value) {
    return String(value || "").replace(/\b([A-Z]{3})\b/g, month => month[0] + month.slice(1).toLowerCase());
  }

  function runoffIconMarkup(name, className = "") {
    const paths = {
      runoff: '<path d="M4 5h5v5H4zM15 5h5v5h-5zM9 7.5h6M12 7.5v9M8 19h8M9 16h6"/>',
      calendar: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M8 3v4M16 3v4M3.5 9.5h17M8 13h.01M12 13h.01M16 13h.01M8 17h.01M12 17h.01"/>',
      observations: '<path d="M4 20V11M9 20V7M14 20V12M19 20V4M2 20h20"/>',
      matchups: '<circle cx="8" cy="8" r="3"/><circle cx="16" cy="8" r="3"/><path d="M2.5 20c.4-4 2.3-6 5.5-6s5.1 2 5.5 6M10.5 20c.4-4 2.3-6 5.5-6s5.1 2 5.5 6"/>',
      pollsters: '<path d="M3 10h18M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 19h18M12 3l9 5H3z"/>',
      target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>'
    };
    const body = paths[name] || paths.runoff;
    return `<svg class="${escapeAttribute(className)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  }

  function runoffCompactSourceLink(url, accessibleLabel) {
    const safe = safeSourceUrl(url);
    return safe
      ? `<a class="hybrid-runoff-source is-compact is-icon-only" href="${escapeAttribute(safe)}" target="_blank" rel="noopener noreferrer" aria-label="${escapeAttribute(accessibleLabel)}"><span aria-hidden="true">↗</span></a>`
      : '<span class="hybrid-runoff-source is-compact is-icon-only">—</span>';
  }

  function groupRunoffHistoryWindows(observations) {
    const windows = [];
    (Array.isArray(observations) ? observations : []).forEach(event => {
      const key = `${event.fieldwork_start}/${event.fieldwork_end}`;
      const current = windows[windows.length - 1];
      if (current?.key === key) current.observations.push(event);
      else windows.push({ key, event, observations: [event] });
    });
    return windows;
  }
  function runoffBalanceRail(observation, candidates) {
    const scores = runoffScoresForCandidates(observation, candidates);
    const left = Number.isFinite(scores[0]) ? Math.max(0, Math.min(100, scores[0])) : 50;
    return `<div class="hybrid-runoff-balance" role="img" aria-label="Reported score: ${escapeAttribute(candidates[0])} ${percent(scores[0])}; ${escapeAttribute(candidates[1])} ${percent(scores[1])}; 50 percent centre reference">
      <span class="hybrid-runoff-balance-left" style="width:${left}%"></span>
      <span class="hybrid-runoff-balance-right"></span>
      <span class="hybrid-runoff-balance-centre" aria-hidden="true"></span>
      <span class="hybrid-runoff-balance-label" aria-hidden="true">50</span>
    </div>`;
  }

  function runoffCompactRail(observation, candidates) {
    const scores = runoffScoresForCandidates(observation, candidates);
    const left = Number.isFinite(scores[0]) ? Math.max(0, Math.min(100, scores[0])) : 50;
    return `<span class="hybrid-runoff-compact-rail" role="img" aria-label="${escapeAttribute(candidates[0])} ${percent(scores[0])}; ${escapeAttribute(candidates[1])} ${percent(scores[1])}">
      <span class="hybrid-runoff-compact-left" style="width:${left}%"></span>
      <span class="hybrid-runoff-compact-right"></span>
      <span class="hybrid-runoff-compact-centre" aria-hidden="true"></span>
    </span>`;
  }
  function observationMarkup(observation, candidates) {
    const scores = runoffScoresForCandidates(observation, candidates);

    const fieldwork = observation.fieldwork_start && observation.fieldwork_end
      ? exactRunoffWindowLabel(observation)
      : "Exact fieldwork unavailable";

    const fieldworkLabel = fieldwork === "Exact fieldwork unavailable"
      ? fieldwork
      : runoffTitleCaseDate(fieldwork);

    const sampleSize =
      observation.sampleSize ??
      observation.sample_size;

    const sampleLabel = Number.isInteger(sampleSize)
      ? runoffSampleLabel(sampleSize)
      : "";

    const tooltip = [
      observation.pollster,
      fieldworkLabel,
      sampleLabel
    ].filter(Boolean).join(" · ");

    return `<article class="hybrid-observation hybrid-runoff-source-observation" title="${escapeAttribute(tooltip)}" data-runoff-hover="RUNOFF_HOVER_METADATA">
      <div class="hybrid-runoff-candidate">
        <span class="hybrid-runoff-candidate-name">${escapeHtml(candidates[0])}</span>
        <span class="hybrid-runoff-candidate-result">${portraitMarkup(candidates[0])}<strong>${percent(scores[0])}</strong></span>
      </div>

      <div class="hybrid-runoff-instrument">
        <div class="hybrid-runoff-observation-head">
          <strong>${escapeHtml(observation.pollster)}</strong>
          <span>${escapeHtml(fieldworkLabel)}${sampleLabel ? ` · ${escapeHtml(sampleLabel)}` : ""}</span>
        </div>

        ${runoffBalanceRail(observation, candidates)}

        ${runoffCompactSourceLink(
          observation.source_url,
          `Open ${observation.pollster} source for ${candidates.join(" versus ")}`
        )}
      </div>

      <div class="hybrid-runoff-candidate is-right">
        <span class="hybrid-runoff-candidate-name">${escapeHtml(candidates[1])}</span>
        <span class="hybrid-runoff-candidate-result"><strong>${percent(scores[1])}</strong>${portraitMarkup(candidates[1])}</span>
      </div>

      <div class="hybrid-runoff-margin-tile">
        <span>MARGIN</span>
        <strong>${number(observation.margin)}</strong>
        <small>pts</small>
      </div>
    </article>`;
  }
  function renderRunoffHeader(model) {
    const footprint = model.archive?.state === "ready" ? model.archive.footprint : null;
    const counters = [
      [footprint?.observationCount ?? "—", "observations"],
      [footprint?.matchupCount ?? "—", "matchups"],
      [footprint?.pollsterCount ?? "—", "pollsters"],
      [footprint?.windowCount ?? "—", "windows"]
    ];
    const explanation = model.status === "agree"
      ? "Both pollsters agree this is the closest tested runoff"
      : model.message || "Current comparison unavailable.";
    return `<header class="hybrid-runoff-evidence-header">
      <div class="hybrid-runoff-title-block">
        <span class="hybrid-runoff-mark">${runoffIconMarkup("runoff", "hybrid-runoff-title-icon")}</span>
        <div><h2>RUNOFF SIGNALS</h2><p>Source-separated second-round evidence · no averages · no forecast</p></div>
      </div>
      <div class="hybrid-runoff-current-scope" aria-label="Current exact-window scope">
        <span class="hybrid-runoff-status is-${escapeAttribute(model.status)}">${escapeHtml(model.statusLabel).toUpperCase()}</span>
        <span class="hybrid-runoff-scope-message">${escapeHtml(explanation)}</span>
        <strong class="hybrid-runoff-date-pill">${runoffIconMarkup("calendar", "hybrid-runoff-inline-icon")}<span>${escapeHtml(runoffTitleCaseDate(model.fieldworkLabel))}</span></strong>
      </div>
      <div class="hybrid-runoff-header-metrics" aria-label="Full archive counts">${counters.map(counter => `<span class="hybrid-runoff-header-metric"><strong>${counter[0]}</strong><small>${counter[1]}</small></span>`).join("")}</div>
    </header>`;
  }
  function renderRunoffClosest(model) {
    if (model.status === "agree" && model.selectedMatchup) {
      const matchup = model.selectedMatchup;
      const narrowest = Math.min(...matchup.observations.map(item => Number(item.margin)));
      return `<section class="hybrid-runoff-module hybrid-runoff-closest" aria-labelledby="hybrid-runoff-closest-title">
        <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">1</span><h3 id="hybrid-runoff-closest-title">CLOSEST TESTED RUNOFF</h3></div><span>Same closest matchup · different reported distance</span></div>
        <h4>${escapeHtml(matchup.candidates.join(" vs "))}</h4>
        <div class="hybrid-runoff-observations">${matchup.observations.map(item => observationMarkup(item, matchup.candidates)).join("")}</div>
        <div class="hybrid-runoff-closest-callout">${runoffIconMarkup("target", "hybrid-runoff-callout-icon")}<strong>NARROWEST OBSERVED MARGIN · ${number(narrowest)} PTS</strong></div>
      </section>`;
    }

    if (["split", "ambiguous"].includes(model.status)) {
      const explanation = model.status === "split"
        ? "Pollsters identify different uniquely closest matchups in the common tested set."
        : "At least one pollster has multiple matchups tied at its minimum reported margin.";
      return `<section class="hybrid-runoff-module hybrid-runoff-closest" aria-labelledby="hybrid-runoff-closest-title">
        <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">1</span><h3 id="hybrid-runoff-closest-title">CLOSEST TESTED RUNOFF</h3></div><span>${escapeHtml(model.statusLabel)}</span></div>
        <p class="hybrid-runoff-local-state">${escapeHtml(explanation)}</p>
        <div class="hybrid-runoff-unresolved-grid">${model.pollsters.map(pollster => `<section class="hybrid-runoff-unresolved-source"><h4>${escapeHtml(pollster.pollster)}</h4>${pollster.closest_matchups.map(matchup => `<div class="hybrid-runoff-unresolved-row"><strong>${escapeHtml(matchup.candidates.join(" vs "))}</strong><span>${escapeHtml(runoffScorePair(matchup.result, matchup.candidates))} · ${number(matchup.result.margin)} pts</span>${sourceLink(matchup.result.source_url, "SOURCE", "hybrid-runoff-source is-compact")}</div>`).join("")}</section>`).join("")}</div>
      </section>`;
    }

    return `<section class="hybrid-runoff-module hybrid-runoff-closest" aria-labelledby="hybrid-runoff-closest-title">
      <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">1</span><h3 id="hybrid-runoff-closest-title">CLOSEST TESTED RUNOFF</h3></div></div>
      <div class="hybrid-runoff-local-state" role="status">No score comparison is shown. A qualifying window requires at least two pollsters, at least two tested matchups per pollster, and at least two exact common matchup keys.</div>
    </section>`;
  }
  function renderRunoffCommonMatchups(model) {
    const pollsters = model.pollsters.map(item => item.pollster);
    const displayMatchups = [...model.commonMatchups].sort((left, right) => {
      const leftSelected = left.matchup_key === model.selectedMatchup?.key;
      const rightSelected = right.matchup_key === model.selectedMatchup?.key;
      if (leftSelected !== rightSelected) return leftSelected ? -1 : 1;
      return left.candidates.join(" ").localeCompare(right.candidates.join(" "), "fr");
    });
    return `<section class="hybrid-runoff-module hybrid-runoff-common" aria-labelledby="hybrid-runoff-common-title">
      <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">2</span><div><h3 id="hybrid-runoff-common-title">CURRENT COMMON MATCHUPS</h3></div></div></div>
      ${model.commonMatchups.length ? `<div class="hybrid-runoff-matrix" role="table" aria-label="Current common matchup source results">
        <div class="hybrid-runoff-matrix-head" role="row"><span role="columnheader">MATCHUP</span>${pollsters.map(name => `<span role="columnheader">${escapeHtml(name)}</span>`).join("")}<span role="columnheader">MARGINS</span></div>
        ${displayMatchups.map(matchup => {
          const selected = model.selectedMatchup?.key === matchup.matchup_key;
          const margins = pollsters.map(name => matchup.results.find(item => item.pollster === name)?.margin);
          return `<div class="hybrid-runoff-matrix-row${selected ? " is-selected" : ""}" role="row">
            <span class="hybrid-runoff-matrix-matchup" role="rowheader">${selected ? '<small>CLOSEST COMMON MATCHUP</small>' : ""}<strong>${escapeHtml(matchup.candidates[0] || "")}<br>vs ${escapeHtml(matchup.candidates[1] || "")}</strong></span>
            ${pollsters.map(name => {
              const result = matchup.results.find(item => item.pollster === name);
              if (!result) return `<span class="hybrid-runoff-matrix-result" role="cell">—</span>`;
              const scores = runoffScoresForCandidates(result, matchup.candidates);
              return `<span class="hybrid-runoff-matrix-result" role="cell"><span class="hybrid-runoff-matrix-score is-left">${percent(scores[0])}</span>${runoffCompactRail(result, matchup.candidates)}<span class="hybrid-runoff-matrix-score is-right">${percent(scores[1])}</span></span>`;
            }).join("")}
            <span class="hybrid-runoff-matrix-margins" role="cell"><strong>${margins.map(value => number(value)).join(" / ")}</strong><small>pts</small></span>
          </div>`;
        }).join("")}
      </div>` : `<div class="hybrid-runoff-local-state" role="status">No common exact-window matchup matrix is available for this status.</div>`}
      <div class="hybrid-runoff-matrix-legend"><span><i class="is-left"></i>Candidate 1</span><span><i class="is-right"></i>Candidate 2</span><span>Exact source-reported scores · no averages</span></div>
    </section>`;
  }
  function renderRunoffFootprint(model) {
    if (model.archive.state !== "ready") {
      return `<section class="hybrid-runoff-module hybrid-runoff-footprint" aria-labelledby="hybrid-runoff-footprint-title"><div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">3</span><h3 id="hybrid-runoff-footprint-title">EVIDENCE FOOTPRINT</h3></div></div><div class="hybrid-runoff-local-state" role="status" aria-live="polite">${escapeHtml(model.archive.message)}</div></section>`;
    }
    const footprint = model.archive.footprint;
    const metrics = [
      [footprint.observationCount, "TOTAL OBSERVATIONS", "observations"],
      [footprint.matchupCount, "DISTINCT MATCHUPS", "matchups"],
      [footprint.pollsterCount, "POLLSTERS REPRESENTED", "pollsters"],
      [footprint.windowCount, "FIELDWORK WINDOWS", "calendar"]
    ];
    const earliestYear = String(footprint.earliestWindow.fieldwork_end).slice(0, 4);
    return `<section class="hybrid-runoff-module hybrid-runoff-footprint" aria-labelledby="hybrid-runoff-footprint-title">
      <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">3</span><h3 id="hybrid-runoff-footprint-title">EVIDENCE FOOTPRINT</h3></div></div>
      <dl class="hybrid-runoff-footprint-grid">${metrics.map(metric => `<div class="hybrid-runoff-metric">${runoffIconMarkup(metric[2], "hybrid-runoff-metric-icon")}<dd><strong>${metric[0]}</strong></dd><dt>${metric[1]}</dt></div>`).join("")}</dl>
      <div class="hybrid-runoff-window-range">
        <article><span>EARLIEST EVIDENCE</span><strong>${escapeHtml(earliestYear)}</strong><b>${escapeHtml(runoffMonthYear(footprint.earliestWindow))}</b><small>${escapeHtml(runoffTitleCaseDate(exactRunoffWindowLabel(footprint.earliestWindow)))}</small></article>
        <article><span>LATEST EVIDENCE</span><strong>${escapeHtml(runoffMonthYear(footprint.latestWindow))}</strong><small>${escapeHtml(runoffTitleCaseDate(exactRunoffWindowLabel(footprint.latestWindow)))}</small></article>
      </div>
      <p class="hybrid-runoff-module-note">Source-linked evidence · no synthesis · no forecast</p>
    </section>`;
  }
  function renderRunoffHistory(model) {
    if (model.archive.state !== "ready") {
      return `<section class="hybrid-runoff-module hybrid-runoff-history" aria-labelledby="hybrid-runoff-history-title"><div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">4</span><h3 id="hybrid-runoff-history-title">SELECTED MATCHUP HISTORY</h3></div></div><div class="hybrid-runoff-local-state" role="status" aria-live="polite">${escapeHtml(model.archive.message)}</div></section>`;
    }

    const selected = model.archive.matchups.find(
      matchup => matchup.key === model.archive.selectedHistoryKey
    );

    const observations = Array.isArray(model.archive.history)
      ? model.archive.history
      : [];

    const candidates =
      selected?.candidates ||
      observations[0]?.candidates ||
      [];

    return `<section class="hybrid-runoff-module hybrid-runoff-history" aria-labelledby="hybrid-runoff-history-title">
      <div class="hybrid-runoff-module-head hybrid-runoff-history-head">
        <div>
          <span class="hybrid-runoff-step" aria-hidden="true">4</span>
          <div>
            <h3 id="hybrid-runoff-history-title">SELECTED MATCHUP HISTORY</h3>
            <p>${escapeHtml(selected?.candidates.join(" vs ") || "Exact matchup")} · Discrete source observations only</p>
          </div>
        </div>

        <label>
          INSPECT MATCHUP
          <select class="hybrid-runoff-history-select" data-hybrid-runoff-history>
            ${model.archive.matchups.map(matchup => `<option value="${escapeAttribute(matchup.key)}"${matchup.key === model.archive.selectedHistoryKey ? " selected" : ""}>${escapeHtml(matchup.candidates.join(" vs "))}</option>`).join("")}
          </select>
        </label>
      </div>

      <div
        class="hybrid-runoff-history-scroll"
        tabindex="0"
        aria-label="Scrollable selected matchup history"
      >
        <div
          class="hybrid-runoff-chronology is-observation-strip"
          aria-label="${observations.length} exact source observations"
        >
          <span
            class="hybrid-runoff-chronology-guide"
            aria-hidden="true"
          ></span>

          ${observations.map((event, index) => {
            const scores = runoffScoresForCandidates(
              event,
              candidates
            );

            return `<div class="hybrid-runoff-history-position">
              <span class="hybrid-runoff-history-node${index % 2 ? " is-violet" : ""}" aria-hidden="true"></span>

              <time datetime="${escapeAttribute(event.fieldwork_end)}">${escapeHtml(runoffTitleCaseDate(exactRunoffWindowLabel(event)))}</time>

              <div class="hybrid-runoff-history-group">
                <article class="hybrid-runoff-history-entry" title="${escapeAttribute(`${runoffTitleCaseDate(exactRunoffWindowLabel(event))} · ${event.pollster} · ${percent(scores[0])}–${percent(scores[1])} · Margin ${number(event.margin)} pts · ${runoffSampleLabel(event.sample_size)}`)}" data-runoff-hover="RUNOFF_HOVER_METADATA">
                  <strong class="hybrid-runoff-history-pollster">${escapeHtml(event.pollster)}${runoffCompactSourceLink(
                      event.source_url,
                      `Open ${event.pollster} source for ${candidates.join(" versus ")}`
                    )}</strong>

                  <span class="hybrid-runoff-history-scores">
                    <b>${percent(scores[0])}</b>
                    <i>–</i>
                    <b>${percent(scores[1])}</b>
                  </span>

                </article>
              </div>
            </div>`;
          }).join("")}
        </div>
      </div>
    </section>`;
  }
  function renderRunoffOtherMatchups(model) {
    if (model.archive.state !== "ready") {
      return `<section class="hybrid-runoff-module hybrid-runoff-others" aria-labelledby="hybrid-runoff-others-title"><div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">5</span><h3 id="hybrid-runoff-others-title">OTHER TESTED MATCHUPS</h3></div></div><div class="hybrid-runoff-local-state" role="status" aria-live="polite">${escapeHtml(model.archive.message)}</div></section>`;
    }
    return `<section class="hybrid-runoff-module hybrid-runoff-others" aria-labelledby="hybrid-runoff-others-title">
      <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">5</span><h3 id="hybrid-runoff-others-title">OTHER TESTED MATCHUPS</h3></div><span>Evidence catalogue · latest reported source result shown</span></div>
      <div class="hybrid-runoff-other-grid">${model.archive.otherMatchups.map(matchup => {
        const event = matchup.latest;
        const scores = runoffScoresForCandidates(event, matchup.candidates);
        const sourceLabel = `Open ${event.pollster} source for ${matchup.candidates.join(" versus ")}`;
        return `<article class="hybrid-runoff-other-card" title="${escapeAttribute(`${event.pollster} · ${runoffTitleCaseDate(exactRunoffWindowLabel(event))} · Margin ${number(event.margin)} pts · ${runoffSampleLabel(event.sample_size)}`)}" data-runoff-hover="RUNOFF_HOVER_METADATA"><h4><span>${escapeHtml(matchup.candidates[0])}</span><small>vs ${escapeHtml(matchup.candidates[1])}</small></h4><span class="hybrid-runoff-other-meta">${escapeHtml(event.pollster)} · ${escapeHtml(runoffTitleCaseDate(exactRunoffWindowLabel(event)))}</span><div class="hybrid-runoff-other-score"><strong>${percent(scores[0])}</strong>${runoffCompactRail(event, matchup.candidates)}<strong>${percent(scores[1])}</strong></div><div class="hybrid-runoff-other-foot"><span>MARGIN · ${number(event.margin)} PTS</span><span>${escapeHtml(runoffSampleLabel(event.sample_size))}</span>${runoffCompactSourceLink(event.source_url, sourceLabel)}</div></article>`;
      }).join("")}</div>
    </section>`;
  }
  function renderRunoffPanel(model) {
    if (model.state !== "ready" && model.status !== "insufficient") {
      return `<div class="hybrid-runoff-local-state" role="status" aria-live="polite">${escapeHtml(model.message || "Runoff evidence is unavailable.")}</div>`;
    }
    return `<div class="hybrid-runoff-workspace">
      ${renderRunoffHeader(model)}
      <div class="hybrid-runoff-current-grid">
        ${renderRunoffClosest(model)}
        ${renderRunoffCommonMatchups(model)}
        ${renderRunoffOtherMatchups(model)}
      </div>
      <div class="hybrid-runoff-archive-grid">
        ${renderRunoffHistory(model)}
      </div>
    </div>`;
  }
  function renderMediaPanel(model) {
    if (model.state !== "ready") {
      return summaryState(model);
    }

    const feedRows = model.feedItems
      .map((item, index) => {
        const rowNumber = String(index + 1).padStart(2, "0");

        return `
          <a
            class="hybrid-media-terminal-row"
            href="${escapeAttribute(safeSourceUrl(item.url))}"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="${escapeAttribute(
              `Open ${item.publisher} article: ${item.headline}`
            )}"
          >
            <span
              class="hybrid-media-terminal-index"
              aria-hidden="true"
            >${rowNumber}</span>

            <time
              datetime="${escapeAttribute(item.published_at)}"
            >${escapeHtml(
              formatNewsDateTime(item.published_at)
            )}</time>

            <span
              class="hybrid-media-terminal-publisher"
            >${escapeHtml(item.publisher)}</span>

            <span class="hybrid-media-terminal-copy">
              <span
                class="hybrid-media-terminal-headline"
                lang="fr"
              >${escapeHtml(item.headline)} <span aria-hidden="true">↗</span></span>
            </span>
          </a>`;
      })
      .join("");

    const maxCandidateShare = Math.max(
      1,
      ...model.candidateCoverageLeaders.flatMap(
        item => [
          number(item.latestShare),
          number(item.previousShare)
        ]
      )
    );

    const candidateRows = !model.candidateCoverageAvailable
      ? `<div class="hybrid-state is-compact">Active-field candidate comparison unavailable.</div>`
      : model.candidateCoverageLeaders
        .map(item => {
          const deltaAvailable = item.changeAvailable === true;
          const delta = item.delta;

          const directionClass = deltaAvailable
            ? delta > 0.05
              ? "is-up"
              : delta < -0.05
                ? "is-down"
                : "is-flat"
            : "";

          const direction = !deltaAvailable
            ? ""
            : delta > 0.05
              ? "▲"
              : delta < -0.05
                ? "▼"
                : "—";

          const deltaText = deltaAvailable
            ? `${delta > 0 ? "+" : ""}${formatMediaShare(delta)}pp`
            : "Comparison unavailable";

          const latestShareText =
            formatMediaShare(item.latestShare);

          const previousShareText =
            formatMediaShare(item.previousShare);

          const currentWidth = Math.min(
            100,
            item.latestShare / maxCandidateShare * 100
          );

          const previousPosition = Math.min(
            100,
            item.previousShare / maxCandidateShare * 100
          );

          return `
            <div
              class="hybrid-candidate-share-row"
              aria-label="${escapeAttribute(
                `${item.name}, ${item.tierLabel}: ${latestShareText} percent active-field candidate-linked share in the latest seven days, ${previousShareText} percent in the previous seven days, ${deltaText}; ${item.latestCount} latest records and ${item.previousCount} previous records`
              )}"
            >
              <span class="hybrid-candidate-share-name">
                ${escapeHtml(item.name)}
              </span>
                <small class="hybrid-status-chip">${escapeHtml(item.tierLabel)}</small>

              <strong>${latestShareText}%</strong>

              <span
                class="hybrid-candidate-share-track"
                aria-hidden="true"
              >
                <span
                  class="hybrid-candidate-share-current"
                  style="--hybrid-current-share:${currentWidth.toFixed(2)}%"
                ></span>

                <i
                  class="hybrid-candidate-share-previous"
                  style="--hybrid-previous-share:${previousPosition.toFixed(2)}%"
                ></i>
              </span>

              <b class="${directionClass}">
                ${direction ? `${direction} ` : ""}${escapeHtml(deltaText)}
              </b>
            </div>`;
        })
        .join("");

    const currentPeriodLabel =
      formatMediaPeriodRange(
        model.latestStartKey,
        model.latestEndKey
      );

    const priorPeriodLabel =
      formatMediaPeriodRange(
        model.previousStartKey,
        model.previousEndKey
      );

    const topicRows =
      model.topicCoverage.length
        ? model.topicCoverage
            .map((topic, index) => {
              const sourceDaysAvailable =
                Number.isFinite(
                  topic.sourceDays
                );

              const publishersAvailable =
                Number.isFinite(
                  topic.publishers
                );

              const itemCountAvailable =
                Number.isFinite(
                  topic.itemCount
                );

              const sourceDaysText =
                sourceDaysAvailable
                  ? String(topic.sourceDays)
                  : "—";

              const publishersText =
                publishersAvailable
                  ? String(topic.publishers)
                  : "—";

              const sourceDaysAccessible =
                sourceDaysAvailable
                  ? countLabel(
                      topic.sourceDays,
                      "source-day"
                    )
                  : "source-day count unavailable";

              const publishersAccessible =
                publishersAvailable
                  ? countLabel(
                      topic.publishers,
                      "publisher"
                    )
                  : "publisher count unavailable";

              const itemContext =
                itemCountAvailable
                  ? `; ${countLabel(
                      topic.itemCount,
                      "item"
                    )}`
                  : "";

              return `
                <button
                  class="hybrid-topic-matrix-row"
                  type="button"
                  data-hybrid-media-topic="${escapeAttribute(topic.id)}"
                  aria-label="${escapeAttribute(
                    `${topic.label}: rank ${index + 1}; ${sourceDaysAccessible}; ${publishersAccessible}${itemContext}. Open Campaign Agenda detail.`
                  )}"
                >
                  <span
                    class="hybrid-topic-matrix-rank"
                    aria-hidden="true"
                  >${String(index + 1).padStart(2, "0")}</span>

                  <span class="hybrid-topic-matrix-label">
                    ${escapeHtml(topic.label)}
                  </span>

                  <strong class="hybrid-topic-matrix-days">
                    ${sourceDaysText}
                  </strong>

                  <strong class="hybrid-topic-matrix-pubs">
                    ${publishersText}
                  </strong>
                </button>`;
            })
            .join("")
        : `<div class="hybrid-state is-compact">No specific sustained topics available.</div>`;

    return `
      <div class="hybrid-media-terminal-layout">
        <section class="hybrid-media-terminal-feed">
          <div class="hybrid-media-terminal-heading">
            <h3 class="hybrid-section-title">
              Recent election coverage
            </h3>

            <span class="hybrid-media-terminal-status">
              ${model.feedItems.length} items ·
              ${model.acceptedNewsPublisherCount} publishers
            </span>
          </div>

          <div
            class="hybrid-media-terminal-list"
            role="feed"
            aria-label="Recent accepted election coverage"
          >
            ${feedRows}
          </div>
        </section>

        <aside class="hybrid-media-terminal-rail">
          <section class="hybrid-media-terminal-module">
            <h3 class="hybrid-section-title">
              Coverage shift
            </h3>

            <div
              class="hybrid-coverage-period-legend"
              role="group"
              aria-label="${escapeAttribute(
                `Coverage comparison. Cyan bars show the current period ${currentPeriodLabel}. Violet markers show the prior period ${priorPeriodLabel}.`
              )}"
            >
              <span class="hybrid-coverage-period">
                <i
                  class="hybrid-coverage-period-swatch is-current"
                  aria-hidden="true"
                ></i>
                <span>
                  <strong>CURRENT</strong>
                  <small>${escapeHtml(currentPeriodLabel)}</small>
                </span>
              </span>

              <span class="hybrid-coverage-period">
                <i
                  class="hybrid-coverage-period-swatch is-prior"
                  aria-hidden="true"
                ></i>
                <span>
                  <strong>PRIOR</strong>
                  <small>${escapeHtml(priorPeriodLabel)}</small>
                </span>
              </span>
            </div>

            <div class="hybrid-candidate-share-list">
              ${candidateRows}
            </div>
          </section>

          <section class="hybrid-media-terminal-module">
            <h3 class="hybrid-section-title">
              Sustained topics
            </h3>

            <span
              class="visually-hidden"
              id="hybrid-topic-matrix-description"
            >
              Topics ranked by the number of source-days on which they appeared. Publisher count indicates reporting breadth.
            </span>

            <div
              class="hybrid-topic-matrix"
              aria-describedby="hybrid-topic-matrix-description"
            >
              <div
                class="hybrid-topic-matrix-head"
                aria-hidden="true"
              >
                <span></span>
                <span></span>
                <strong>DAYS</strong>
                <strong>PUBS</strong>
              </div>

              ${topicRows}
            </div>
          </section>
        </aside>
      </div>`;
  }

  function renderAgendaPanel(model) {
    if (model.state !== "ready") return summaryState(model);
    const selected = model.selectedTopic;
    const definitionAvailable = typeof selected.definition === "string" && Boolean(selected.definition.trim());
    const definition = definitionAvailable
      ? selected.definition.trim()
      : "Topic definition unavailable in the current repository data.";
    return `<div class="hybrid-agenda-layout">
      <section class="hybrid-agenda-ranking">
        <h3 class="hybrid-section-title">Eligible-topic ranking</h3>
        <p class="hybrid-section-sub">Accepted election-news topics · ${model.windowDays}-day source window. Primary bar value: source-day recurrence.</p>
        ${model.topics.map((topic, index) => `
          <button class="hybrid-agenda-topic" type="button" data-hybrid-agenda-topic="${escapeAttribute(topic.id)}" aria-pressed="${String(topic.id === selected.id)}">
            <span class="hybrid-agenda-topic-head"><span>${index + 1}. ${escapeHtml(topic.label)}</span><strong>${topic.source_day_count} source-days</strong></span>
            <span class="hybrid-agenda-topic-meta">${countLabel(topic.item_count, "item")} · ${countLabel(topic.publisher_count, "publisher")} · ${countLabel(topic.active_day_count, "active day")}</span>
            <span class="hybrid-track" aria-hidden="true"><span class="hybrid-fill" style="--hybrid-width:${(number(topic.source_day_count) / model.maxSourceDays * 100).toFixed(1)}%"></span></span>
          </button>`).join("")}
      </section>
      <section class="hybrid-agenda-detail" aria-live="polite">
        <div class="hybrid-section-title">Selected recurring topic</div>
        <h3>${escapeHtml(selected.label)}</h3>
        <p class="hybrid-agenda-definition${definitionAvailable ? "" : " is-unavailable"}">${escapeHtml(definition)}</p>
        <div class="hybrid-metrics">
          <span class="hybrid-metric">${selected.source_day_count} source-days</span>
          <span class="hybrid-metric">${countLabel(selected.item_count, "accepted item")}</span>
          <span class="hybrid-metric">${countLabel(selected.publisher_count, "publisher")}</span>
          <span class="hybrid-metric">${countLabel(selected.active_day_count, "active day")}</span>
        </div>
        <div class="hybrid-supporting-list">${selected.supporting_items.slice(0, 5).map(item => `
          <a class="hybrid-supporting-link" href="${escapeAttribute(safeSourceUrl(item.url))}" target="_blank" rel="noopener noreferrer">
            <span class="hybrid-supporting-meta">${escapeHtml(item.publisher)} · ${formatDay(item.published_at)}</span>
            <span lang="fr">${escapeHtml(item.headline)} <span aria-hidden="true">↗</span></span>
          </a>`).join("") || '<div class="hybrid-state is-compact">No supporting source-linked items are available for this topic.</div>'}</div>
      </section>
    </div>
    <p class="hybrid-disclosure">Recurring campaign topics classify accepted presidential-election coverage from monitored publishers. Bars use source-day count, not raw article volume. This is agenda activity, not voter or public priorities.</p>`;
  }

  function filteredClaimReviews(model) {
    const hasAssociationFilter = Boolean(state.claimsCandidateId) || state.claimsRelationship !== "all";
    return model.reviews.filter(review => {
      const associationMatches = !hasAssociationFilter || review.candidate_associations.some(item =>
        (!state.claimsCandidateId || item.candidate_id === state.claimsCandidateId) &&
        (state.claimsRelationship === "all" || item.relationship === state.claimsRelationship)
      );
      return associationMatches && (!state.claimsPublisher || review.publisher_name === state.claimsPublisher);
    });
  }

  function renderClaimRows(filteredReviews) {
    const visibleReviews = filteredReviews.slice(0, 8);
    if (!visibleReviews.length) return '<div class="hybrid-state is-compact">No validated reviews match these filters.</div>';
    return visibleReviews.map(review => {
      const rating = ratingDisplay(review);
      return `<article class="hybrid-claim-row">
        <time class="hybrid-claim-date" datetime="${escapeAttribute(review.review_date)}">${formatDay(review.review_date)}</time>
        <div class="hybrid-claim-associations">${review.candidate_associations.map(item => `<span class="hybrid-claim-association"><b>${item.relationship.toUpperCase()}</b> ${escapeHtml(item.candidate_name)}</span>`).join("")}</div>
        <div class="hybrid-claim-text" lang="fr">${escapeHtml(review.claim_text)}</div>
        <div class="hybrid-claim-rating-cell"><span class="hybrid-rating" data-rating-family="${escapeAttribute(rating.family)}">${escapeHtml(rating.label)}</span><span class="hybrid-original-rating" lang="fr">Publisher: ${escapeHtml(rating.original)}</span></div>
        <div class="hybrid-claim-publisher">${escapeHtml(review.publisher_name)}${sourceLink(review.review_url, "Read review", "hybrid-claim-source", `Read ${review.publisher_name} review dated ${formatDay(review.review_date)}`)}</div>
      </article>`;
    }).join("");
  }

  function renderClaimsPanel(model) {
    if (model.state !== "ready") return summaryState(model);
    const filteredReviews = filteredClaimReviews(model);
    const filteredCount = filteredReviews.length;
    const visibleCount = Math.min(8, filteredCount);
    const resultStatus = filteredCount > 8
      ? `Showing latest ${visibleCount} of ${filteredCount} matching reviews`
      : `Showing latest ${visibleCount} matching ${visibleCount === 1 ? "review" : "reviews"}`;
    return `<div class="hybrid-claims-topline">
      <div class="hybrid-claim-stat"><strong>${model.reviewCount}</strong>validated reviews</div>
      <div class="hybrid-claim-stat"><strong>${model.byAssociations}</strong>BY associations</div>
      <div class="hybrid-claim-stat"><strong>${model.aboutAssociations}</strong>ABOUT associations</div>
      <div class="hybrid-claim-stat"><strong>${model.totalAssociations}</strong>total associations</div>
      <div class="hybrid-claim-stat"><strong>${model.coveredCandidateCount}</strong>candidates covered</div>
    </div>
    <div class="hybrid-claims-strip-wrap">
      <div>
        <div class="hybrid-relation-strip" role="img" aria-label="${model.byAssociations} BY associations and ${model.aboutAssociations} ABOUT associations out of ${model.totalAssociations} total candidate associations">
          <span class="hybrid-relation-by" style="--hybrid-by:${model.byPercent.toFixed(2)}%"></span>
          <span class="hybrid-relation-about" style="--hybrid-about:${model.aboutPercent.toFixed(2)}%"></span>
        </div>
        <div class="hybrid-relation-legend"><span><strong>${model.byPercent.toFixed(0)}%</strong> BY associations</span><span><strong>${model.aboutPercent.toFixed(0)}%</strong> ABOUT associations</span></div>
      </div>
      <span class="hybrid-summary-meta">Latest review <strong>${formatDay(model.latestReviewDate)}</strong></span>
    </div>
    <div class="hybrid-claims-controls" aria-label="Filter Claim Scrutiny reviews">
      <div class="hybrid-relationship-filters" role="group" aria-label="Candidate relationship">
        ${["all", "by", "about"].map(value => `<button class="hybrid-filter-button" type="button" data-hybrid-claims-relationship="${value}" aria-pressed="${String(state.claimsRelationship === value)}">${value === "all" ? "ALL REVIEWS" : value.toUpperCase() + " ASSOCIATIONS"}</button>`).join("")}
      </div>
      <label class="hybrid-select-label">Candidate
        <select class="hybrid-select" data-hybrid-claims-candidate>
          <option value="">All candidates</option>
          ${model.candidates.map(item => `<option value="${escapeAttribute(item.id)}"${item.id === state.claimsCandidateId ? " selected" : ""}>${escapeHtml(item.name)}</option>`).join("")}
        </select>
      </label>
      <label class="hybrid-select-label">Publisher
        <select class="hybrid-select" data-hybrid-claims-publisher>
          <option value="">All publishers</option>
          ${model.publisherNames.map(name => `<option value="${escapeAttribute(name)}"${name === state.claimsPublisher ? " selected" : ""}>${escapeHtml(name)}</option>`).join("")}
        </select>
      </label>
      <span class="hybrid-summary-meta hybrid-claims-result-status" aria-live="polite">${resultStatus}</span>
    </div>
    <p class="hybrid-filter-scope">Filters affect the review rows below. The candidate matrix shows full-archive association totals.</p>
    <div class="hybrid-claims-layout">
      <section class="hybrid-claims-matrix">
        <h3 class="hybrid-section-title">Candidate association matrix</h3>
        <div class="hybrid-matrix-head"><span>Candidate</span><span>BY</span><span>ABOUT</span></div>
        ${model.candidates.map(item => `<div class="hybrid-matrix-row"><span>${escapeHtml(item.name)}</span><span class="hybrid-matrix-value is-by">${item.by}</span><span class="hybrid-matrix-value is-about">${item.about}</span></div>`).join("")}
      </section>
      <section class="hybrid-claim-rows">
        <h3 class="hybrid-section-title">Latest validated review rows</h3>
        ${renderClaimRows(filteredReviews)}
      </section>
    </div>
    <p class="hybrid-disclosure">The relationship strip denominator is ${model.totalAssociations} candidate associations: ${model.byAssociations} BY plus ${model.aboutAssociations} ABOUT. It is not calculated against review count. Ratings prefer repository English display fields when present and otherwise retain the existing French-to-English normalization fallback; the original publisher rating remains visible.</p>`;
  }

  function renderFocusWorkspace(models) {
    return `<section class="hybrid-workspace" data-hybrid-workspace aria-label="Signal Board focus workspace">
      <div class="hybrid-tabs" role="tablist" aria-label="Lower evidence workspace" aria-orientation="horizontal">
        ${viewOrder.map(key => `<button class="hybrid-tab" id="${views[key].tabId}" type="button" role="tab"
          data-hybrid-view="${key}" aria-controls="${views[key].panelId}" aria-selected="${String(state.activeView === key)}" tabindex="${state.activeView === key ? "0" : "-1"}">${views[key].label}</button>`).join("")}
      </div>
      <section class="hybrid-panel" id="signal-runoff-panel" role="tabpanel" aria-labelledby="signal-runoff-tab"${state.activeView === "runoff" ? "" : " hidden"}>${renderRunoffPanel(models.runoff)}</section>
      <section class="hybrid-panel" id="signal-candidates-panel" role="tabpanel" aria-labelledby="signal-candidates-tab"${state.activeView === "candidates" ? "" : " hidden"}>
        <div id="candidate-signals-root" data-candidate-signals-state="${state.candidateSignals.status}">
          <div class="candidate-signals-state" role="status" aria-live="polite">Loading candidate evidence…</div>
        </div>
      </section>
      <section class="hybrid-panel" id="signal-events-panel" role="tabpanel" aria-labelledby="signal-events-tab"${state.activeView === "events" ? "" : " hidden"}>
        <h2 class="hybrid-section-title">CAMPAIGN EVENTS</h2>
        <div class="hybrid-state">Campaign Events is not yet available.</div>
      </section>
      <section class="hybrid-panel" id="signal-agenda-panel" role="tabpanel" aria-labelledby="signal-agenda-tab"${state.activeView === "agenda" ? "" : " hidden"}>${renderAgendaPanel(models.agenda)}</section>
      <section class="hybrid-panel" id="signal-claims-panel" role="tabpanel" aria-labelledby="signal-claims-tab"${state.activeView === "claims" ? "" : " hidden"}>${renderClaimsPanel(models.claims)}</section>
    </section>`;
  }

  function resolveCandidateSignalsPortrait(candidateId) {
    const candidate = state.candidateSignals.candidates.find(
      item => item.candidate_id === candidateId
    );
    return candidate
      ? candidatePortraits[candidate.candidate_name] || null
      : null;
  }

  function renderCandidateSignalsPanel() {
    const candidateMount = document.getElementById(
      "candidate-signals-root"
    );
    const renderer =
      window.France2027CandidateSignalsWorkspace;
    if (!candidateMount || !renderer) return null;

    const selectedCandidateId = renderer.render(
      candidateMount,
      state.candidateSignals,
      {
        selectedCandidateId:
          state.selectedCandidateSignalsId,
        onSelect(candidateId) {
          state.selectedCandidateSignalsId =
            candidateId;
          renderCandidateSignalsPanel();
        },
        resolvePortrait:
          resolveCandidateSignalsPortrait
      }
    );
    state.selectedCandidateSignalsId =
      selectedCandidateId;
    return selectedCandidateId;
  }

  function setActiveSignalView(view, options = {}) {
    if (!views[view]) view = defaultView;
    state.activeView = view;
    mount.querySelectorAll("[data-hybrid-card]").forEach(card => {
      const active = card.dataset.hybridCard === view;
      card.classList.toggle("is-selected", active);
      card.setAttribute("aria-pressed", String(active));
    });
    let activeTab = null;
    mount.querySelectorAll("[role='tab'][data-hybrid-view]").forEach(tab => {
      const active = tab.dataset.hybridView === view;
      if (active) activeTab = tab;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      if (panel) panel.hidden = !active;
    });
    if (activeTab) revealActiveTab(activeTab);
    if (options.focusTab) activeTab?.focus();
    if (options.scrollWorkspace) scrollWorkspaceIfNeeded(view);
  }

  function revealActiveTab(tab) {
    const container = tab.closest(".hybrid-tabs");
    if (!container || container.scrollWidth <= container.clientWidth) return;
    const containerRect = container.getBoundingClientRect();
    const tabRect = tab.getBoundingClientRect();
    const visibleLeft = containerRect.left + container.clientLeft;
    const visibleRight = visibleLeft + container.clientWidth;
    let delta = 0;
    if (tabRect.left < visibleLeft) delta = tabRect.left - visibleLeft;
    else if (tabRect.right > visibleRight) delta = tabRect.right - visibleRight;
    if (Math.abs(delta) < 1) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    container.scrollTo({ left: container.scrollLeft + delta, behavior: reduced ? "auto" : "smooth" });
  }

  function setViewHash(view, source) {
    if (!views[view]) view = defaultView;
    state.scrollOnNextHash = source === "card" || (source === "tab" && view === "pollCompare");
    if (window.location.hash === views[view].hash) {
      setActiveSignalView(view, { scrollWorkspace: state.scrollOnNextHash });
      state.scrollOnNextHash = false;
      return;
    }
    window.location.hash = views[view].hash;
  }

  function scrollWorkspaceIfNeeded(view = state.activeView) {
    const target = view === "pollCompare"
      ? document.getElementById("polling-evidence-lab")
      : mount.querySelector("[data-hybrid-workspace]");
    if (!target) return;
    const rect = target.getBoundingClientRect();
    if (rect.top >= 0 && rect.top < window.innerHeight * .82) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
  }

  function bindMediaTopicLinks(root = mount) {
    root
      .querySelectorAll(
        "[data-hybrid-media-topic]"
      )
      .forEach(button => {
        button.addEventListener(
          "click",
          () => {
            state.selectedAgendaTopicId =
              button.dataset
                .hybridMediaTopic;

            state.activeView =
              "agenda";

            if (
              window.location.hash !==
              views.agenda.hash
            ) {
              window.location.hash =
                views.agenda.hash;
            }

            renderAll();
          }
        );
      });
  }
  function bindInteractions() {
    bindMediaTopicLinks();

    mount.querySelectorAll("[data-hybrid-card]").forEach(card => {
      card.addEventListener("click", () => setViewHash(card.dataset.hybridCard, "card"));
    });

    const tabs = [...mount.querySelectorAll("[role='tab'][data-hybrid-view]")];
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => setViewHash(tab.dataset.hybridView, "tab"));
      tab.addEventListener("keydown", event => {
        let nextIndex = null;
        if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "Home") nextIndex = 0;
        if (event.key === "End") nextIndex = tabs.length - 1;
        if (nextIndex === null) return;
        event.preventDefault();
        const next = tabs[nextIndex].dataset.hybridView;
        setViewHash(next, "tab");
        setActiveSignalView(next, { focusTab: true });
      });
    });

    mount.querySelectorAll("[data-hybrid-agenda-topic]").forEach(button => {
      button.addEventListener("click", () => {
        state.selectedAgendaTopicId = button.dataset.hybridAgendaTopic;
        renderAll();
        document.querySelector(`[data-hybrid-agenda-topic="${CSS.escape(state.selectedAgendaTopicId)}"]`)?.focus();
      });
    });

    mount.querySelectorAll("[data-hybrid-claims-relationship]").forEach(button => {
      button.addEventListener("click", () => {
        state.claimsRelationship = button.dataset.hybridClaimsRelationship;
        renderAll();
        document.querySelector(`[data-hybrid-claims-relationship="${state.claimsRelationship}"]`)?.focus();
      });
    });

    const candidateFilter = mount.querySelector("[data-hybrid-claims-candidate]");
    if (candidateFilter) candidateFilter.addEventListener("change", event => {
      state.claimsCandidateId = event.target.value;
      renderAll();
      mount.querySelector("[data-hybrid-claims-candidate]")?.focus();
    });

    const publisherFilter = mount.querySelector("[data-hybrid-claims-publisher]");
    if (publisherFilter) publisherFilter.addEventListener("change", event => {
      state.claimsPublisher = event.target.value;
      renderAll();
      mount.querySelector("[data-hybrid-claims-publisher]")?.focus();
    });

    const runoffHistory = mount.querySelector("[data-hybrid-runoff-history]");
    if (runoffHistory) runoffHistory.addEventListener("change", event => {
      state.selectedRunoffHistoryKey = event.target.value;
      renderAll();
      mount.querySelector("[data-hybrid-runoff-history]")?.focus();
    });
  }

  function topMediaComparisonPresentation(model) {
    const available =
      model.candidateCoverageAvailable &&
      model.comparisonQuality?.status ===
      "comparable";
    const reason =
      model.comparisonQuality?.reason || "";
    const reasonLabel =
      reason === "publisher_panel_changed"
        ? "publisher panel changed"
        : reason === "insufficient_data"
          ? "insufficient data"
          : "comparison unavailable";

    return {
      available,
      label: available
        ? "Δ pp"
        : model.candidateCoverageAvailable
          ? "RAW Δ pp"
          : "UNAVAILABLE",
      explanation: available
        ? "Comparable active-field percentage-point change."
        : model.candidateCoverageAvailable
          ? `Raw arithmetic current-minus-prior differences are displayed because comparison quality is not comparable; reason: ${reason || "unknown"}. These values are descriptive and are not comparable trend estimates.`
          : "Active-field candidate comparison unavailable."
    };
  }

  function syncTopMediaShiftQualityLabel(label) {
    const selector =
      ".top-media-shift .top-media-section-heading::after";
    let updatedRules = 0;

    [...document.styleSheets].forEach(styleSheet => {
      let rules;
      try {
        rules = [...styleSheet.cssRules];
      } catch (error) {
        return;
      }

      rules.forEach(rule => {
        if (
          rule.selectorText !== selector ||
          !rule.style?.content
        ) {
          return;
        }
        rule.style.content = JSON.stringify(label);
        updatedRules += 1;
      });
    });

    return updatedRules;
  }
  function renderTopMediaPulsePanel(model) {

    if (model.state !== "ready") {
      return summaryState(model);
    }

    const compactTimestamp = value => {
      const parsed = new Date(value);

      if (!Number.isFinite(parsed.getTime())) {
        return "Date unavailable";
      }

      return new Intl.DateTimeFormat(
        "en-GB",
        {
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
          timeZone: "Europe/Paris"
        }
      )
        .format(parsed)
        .replace(",", "");
    };

    const coverageRows = model.feedItems
      .slice(0, 20)
      .map(item => `
        <a
          class="top-media-coverage-row"
          href="${escapeAttribute(
            safeSourceUrl(item.url)
          )}"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="${escapeAttribute(
            `Open ${item.publisher} article: ${item.headline}`
          )}"
        >
          <span class="top-media-coverage-meta">
            <time
              datetime="${escapeAttribute(
                item.published_at
              )}"
            >${escapeHtml(
              compactTimestamp(
                item.published_at
              )
            )}</time>

            <strong>
              ${escapeHtml(item.publisher)}
            </strong>
          </span>

          <span class="top-media-coverage-copy">
            <span
              class="top-media-coverage-headline"
              lang="fr"
            >${escapeHtml(item.headline)}</span>

            <span class="top-media-source-link">
              Open source ↗
            </span>
          </span>
        </a>
      `)
      .join("");

    const maxCombinedShare = Math.max(
      1,
      ...model.candidateCoverageLeaders.map(
        item =>
          number(item.latestShare) +
          number(item.previousShare)
      )
    );

    const candidateComparison =
      topMediaComparisonPresentation(model);
    const candidateComparisonAvailable =
      candidateComparison.available;
    const candidateComparisonLabel =
      candidateComparison.label;
    const candidateComparisonExplanation =
      candidateComparison.explanation;

    const shiftRows = !model.candidateCoverageAvailable
      ? `<div class="hybrid-state is-compact">Active-field candidate comparison unavailable.</div>`
      : model.candidateCoverageLeaders
          .slice(0, 6)
          .map(item => {
            const deltaAvailable =
              item.changeAvailable === true;
            const rawDeltaAvailable =
              !deltaAvailable &&
              Number.isFinite(item.latestShare) &&
              Number.isFinite(item.previousShare);
            const displayedDelta = deltaAvailable
              ? item.delta
              : rawDeltaAvailable
                ? item.latestShare - item.previousShare
                : null;
            const directionClass =
              displayedDelta === null
                ? "is-limited"
                : displayedDelta > 0.05
                  ? "is-up"
                  : displayedDelta < -0.05
                    ? "is-down"
                    : "is-flat";
            const direction =
              displayedDelta === null
                ? ""
                : displayedDelta > 0.05
                  ? "▲"
                  : displayedDelta < -0.05
                    ? "▼"
                    : "—";
            const latestShareText =
              Number.isFinite(item.latestShare)
                ? formatMediaShare(item.latestShare)
                : "—";
            const previousShareText =
              Number.isFinite(item.previousShare)
                ? formatMediaShare(item.previousShare)
                : "—";
            const deltaText =
              displayedDelta === null
                ? "—"
                : `${displayedDelta > 0 ? "+" : ""}${formatMediaShare(displayedDelta)}pp`;
            const currentWidth = Math.min(
              100,
              number(item.latestShare) / maxCombinedShare * 100
            );
            const previousWidth = Math.min(
              100,
              number(item.previousShare) / maxCombinedShare * 100
            );

            return `
              <button
                class="top-media-shift-row"
                type="button"
                data-hybrid-media-candidate="${escapeAttribute(item.name)}"
                aria-haspopup="dialog"
                aria-controls="topic-coverage-modal"
                aria-expanded="false"
                aria-label="${escapeAttribute(
                  deltaAvailable
                    ? `${item.name}, ${item.tierLabel}: ${latestShareText} percent active-field candidate-linked share in the current period, ${previousShareText} percent in the prior period, comparable change ${deltaText}`
                    : rawDeltaAvailable
                      ? `${item.name}, ${item.tierLabel}: ${latestShareText} percent active-field candidate-linked share in the current period, ${previousShareText} percent in the prior period, raw arithmetic difference ${deltaText}. Publisher panels changed, so this is not a comparable trend estimate.`
                      : `${item.name}, ${item.tierLabel}: ${latestShareText} percent active-field candidate-linked share in the current period, ${previousShareText} percent in the prior period.`
                )}"
              >
                <span class="top-media-shift-name">
                  ${escapeHtml(item.name)}
                  <small class="hybrid-status-chip">${escapeHtml(item.tierLabel)}</small>
                </span>
                <strong>${latestShareText}${latestShareText === "—" ? "" : "%"}</strong>
                <span class="top-media-shift-track" aria-hidden="true">
                  <span
                    class="top-media-shift-current"
                    style="--top-current-share:${currentWidth.toFixed(2)}%"
                  ></span>
                  <i
                    class="top-media-shift-prior"
                    style="--top-prior-share:${previousWidth.toFixed(2)}%"
                  ></i>
                </span>
                <em class="top-media-shift-prior-value">
                  ${previousShareText}${previousShareText === "—" ? "" : "%"}
                </em>
                <b class="${directionClass}" aria-hidden="true">
                  ${displayedDelta === null
                    ? "—"
                    : direction + " " + escapeHtml(deltaText)}
                </b>
              </button>
            `;
          })
          .join("");

    const maxTopicDays = Math.max(
      1,
      ...model.topicCoverage.map(
        topic =>
          Number.isFinite(topic.sourceDays)
            ? topic.sourceDays
            : 0
      )
    );

    const topicRows = model.topicCoverage
      .slice(0, 4)
      .map(topic => {
        const sourceDays =
          Number.isFinite(topic.sourceDays)
            ? topic.sourceDays
            : 0;

        const topicWidth = Math.min(
          100,
          sourceDays /
            maxTopicDays *
            100
        );

        return `
          <button
            class="top-media-topic-row"
            type="button"
            data-hybrid-media-topic="${escapeAttribute(
              topic.id
            )}"
            aria-haspopup="dialog"
            aria-controls="topic-coverage-modal"
            aria-expanded="false"
            aria-label="${escapeAttribute(
              `${topic.label}: ${sourceDays} source-days. Open topic coverage detail.`
            )}"
          >
            <span>
              ${escapeHtml(topic.label)}
            </span>

            <i aria-hidden="true">
              <b
                style="--top-topic-width:${topicWidth.toFixed(2)}%"
              ></b>
            </i>

            <strong>${sourceDays || "—"}</strong>
          </button>
        `;
      })
      .join("");

    const publisherRows =
      model.topPublishers
        .slice(0, 5)
        .map(
          (publisher, index) => `
            <div class="top-media-publisher-row">
              <span aria-hidden="true">
                ${String(index + 1).padStart(2, "0")}
              </span>

              <strong>
                ${escapeHtml(publisher.name)}
              </strong>

              <b>${publisher.count}</b>
            </div>
          `
        )
        .join("");

    const currentPeriodLabel =
      formatMediaPeriodRange(
        model.latestStartKey,
        model.latestEndKey
      );

    const priorPeriodLabel =
      formatMediaPeriodRange(
        model.previousStartKey,
        model.previousEndKey
      );

    return `
      <div class="top-media-dashboard">
        <div
          class="top-media-tabs"
          role="tablist"
          aria-label="Media Pulse views"
        >
          <button
            id="top-media-overview-tab"
            class="is-active"
            type="button"
            role="tab"
            aria-selected="true"
            aria-controls="top-media-overview-panel"
            tabindex="0"
            data-top-media-tab="overview"
          >
            Overview
          </button>

          <button
            id="top-media-coverage-tab"
            type="button"
            role="tab"
            aria-selected="false"
            aria-controls="top-media-coverage-panel"
            tabindex="-1"
            data-top-media-tab="coverage"
          >
            Coverage
          </button>
        </div>

        <section
          id="top-media-coverage-panel"
          class="top-media-tab-panel top-media-latest"
          role="tabpanel"
          aria-labelledby="top-media-coverage-tab"
          data-top-media-panel="coverage"
          hidden
        >
          <div class="top-media-section-heading">
            <h3>Latest election coverage</h3>

            <span>
              ${Math.min(
                5,
                model.feedItems.length
              )} latest
            </span>
          </div>

          <div
            class="top-media-coverage-list"
            role="feed"
            aria-label="Latest accepted election coverage"
          >
            ${coverageRows}
          </div>


          <button
            class="top-media-panel-link ecm-open media-pulse-dashboard-cta"
            type="button"
            data-election-coverage-open
            aria-haspopup="dialog"
            aria-controls="election-coverage-modal"
            aria-expanded="false"
          >
            Browse recent coverage →
          </button>
        </section>

        <aside
          id="top-media-overview-panel"
          class="top-media-tab-panel is-active top-media-analysis"
          role="tabpanel"
          aria-labelledby="top-media-overview-tab"
          data-top-media-panel="overview"
        >
          <section class="top-media-shift">
            <div
              class="top-media-section-heading"
              aria-label="${escapeAttribute(`Active-field coverage shift. ${candidateComparisonExplanation}`)}"
            >
              <h3>Active-field coverage shift</h3>

              <span
                class="top-media-shift-quality"
                title="${escapeAttribute(candidateComparisonExplanation)}"
                aria-label="${escapeAttribute(candidateComparisonExplanation)}"
              >
                ${escapeHtml(candidateComparisonLabel)}
              </span>
            </div>


            <div
              class="top-media-period-legend"
              aria-label="${escapeAttribute(
                `Active-field candidate-linked share. Current period ${currentPeriodLabel}; prior period ${priorPeriodLabel}.`
              )}"
            >
              <span class="is-current">
                <i aria-hidden="true"></i>
                <strong>CURRENT</strong>
                <small>
                  ${escapeHtml(
                    currentPeriodLabel
                  )}
                </small>
              </span>

              <span class="is-prior">
                <i aria-hidden="true"></i>
                <strong>PRIOR</strong>
                <small>
                  ${escapeHtml(
                    priorPeriodLabel
                  )}
                </small>
              </span>
            </div>

            <div class="top-media-shift-list">
              ${shiftRows}
            </div>
          </section>

          <div class="top-media-support-grid">
            <section>
              <div class="top-media-section-heading">
                <h3>Topic coverage</h3>
              </div>

              <div class="top-media-topic-list">
                ${topicRows}
              </div>

            </section>

            <section>
              <div class="top-media-section-heading">
                <h3>Top publishers</h3>
              </div>

              <div class="top-media-publisher-list">
                ${publisherRows}
              </div>
            </section>
          </div>

          <button
            class="top-media-panel-link tcm-open media-pulse-dashboard-cta"
            type="button"
            data-topic-coverage-open
            aria-haspopup="dialog"
            aria-controls="topic-coverage-modal"
            aria-expanded="false"
          >
            Open coverage analysis →
          </button>
        </aside>
      </div>
    `;
  }


  function bindTopMediaTabs() {
    if (!topMediaMount) return;

    const tabs = [
      ...topMediaMount.querySelectorAll(
        "[data-top-media-tab]"
      )
    ];

    const panels = [
      ...topMediaMount.querySelectorAll(
        "[data-top-media-panel]"
      )
    ];

    if (!tabs.length || !panels.length) {
      return;
    }

    const activate = (
      requestedView,
      moveFocus = false
    ) => {
      const activeView =
        requestedView === "overview"
          ? "overview"
          : "coverage";

      tabs.forEach(tab => {
        const selected =
          tab.dataset.topMediaTab ===
          activeView;

        tab.classList.toggle(
          "is-active",
          selected
        );

        tab.setAttribute(
          "aria-selected",
          String(selected)
        );

        tab.tabIndex =
          selected
            ? 0
            : -1;
      });

      panels.forEach(panel => {
        const selected =
          panel.dataset.topMediaPanel ===
          activeView;

        panel.classList.toggle(
          "is-active",
          selected
        );

        panel.hidden = !selected;

        /*
         * Explicit runtime display state
         * prevents older layout rules from
         * exposing both tab panels.
         */
        panel.style.display =
          selected
            ? ""
            : "none";
      });

      if (moveFocus) {
        tabs
          .find(
            tab =>
              tab.dataset.topMediaTab ===
              activeView
          )
          ?.focus();
      }
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener(
        "click",
        () => {
          activate(
            tab.dataset.topMediaTab
          );
        }
      );

      tab.addEventListener(
        "keydown",
        event => {
          const supportedKeys = [
            "ArrowLeft",
            "ArrowRight",
            "Home",
            "End"
          ];

          if (
            !supportedKeys.includes(
              event.key
            )
          ) {
            return;
          }

          event.preventDefault();

          let nextIndex = index;

          if (event.key === "Home") {
            nextIndex = 0;
          } else if (event.key === "End") {
            nextIndex =
              tabs.length - 1;
          } else if (
            event.key === "ArrowRight"
          ) {
            nextIndex =
              (index + 1) %
              tabs.length;
          } else {
            nextIndex =
              (
                index -
                1 +
                tabs.length
              ) %
              tabs.length;
          }

          activate(
            tabs[nextIndex]
              .dataset.topMediaTab,
            true
          );
        }
      );
    });

    activate("overview");
  }

  function bindElectionCoverageModal(
    model
  ) {
    const button = topMediaMount
      ?.querySelector(
        "[data-election-coverage-open]"
      );

    if (!button) return;

    button.addEventListener(
      "click",
      event => {
        event.preventDefault();
        event.stopPropagation();

        window
          .France2027ElectionCoverageModal
          ?.open(model, button);
      }
    );
  }



  function bindTopicCoverageModal(
    mediaModel,
    agendaModel
  ) {
    const buttons = topMediaMount
      ?.querySelectorAll(
        [
          "[data-topic-coverage-open]",
          "[data-hybrid-media-topic]",
          "[data-hybrid-media-candidate]"
        ].join(", ")
      );

    if (!buttons?.length) return;

    buttons.forEach(button => {
      button.addEventListener(
        "click",
        event => {
          event.preventDefault();
          event.stopPropagation();

          const candidateName =
            button.dataset
              .hybridMediaCandidate || "";

          const topicId =
            button.dataset
              .hybridMediaTopic || "";

          window
            .France2027TopicCoverageModal
            ?.open(
              {
                media: mediaModel,
                agenda: agendaModel
              },
              button,
              {
                initialView: candidateName
                  ? "candidates"
                  : "topics",
                candidateName,
                topicId
              }
            );
        }
      );
    });
  }

  function renderTopMediaPulse(model, agendaModel) {
    if (!topMediaMount) return;

    const candidateComparison =
      topMediaComparisonPresentation(model);

    topMediaMount.innerHTML =
      renderTopMediaPulsePanel(model);
    syncTopMediaShiftQualityLabel(candidateComparison.label);

    if (topMediaMetrics) {
      if (model.state === "ready") {
        const metrics = [
          {
            value: model.electionNewsCount,
            label: "accepted news"
          },
          {
            value:
              model.acceptedNewsPublisherCount,
            label: "publishers"
          },
          {
            value: model.activityItemCount,
            label: "recent (14d)"
          },
          {
            value: model.candidateWatchCount,
            label: "candidate-watch"
          }
        ];

        topMediaMetrics.innerHTML =
          metrics
            .map(metric => `
              <span class="top-media-header-metric">
                <strong>
                  ${escapeHtml(
                    String(metric.value)
                  )}
                </strong>
                <small>
                  ${escapeHtml(metric.label)}
                </small>
              </span>
            `)
            .join("");

        topMediaMetrics.setAttribute(
          "aria-label",
          metrics
            .map(
              metric =>
                `${metric.value} ${metric.label}`
            )
            .join("; ")
        );
      } else {
        topMediaMetrics.textContent =
          model.message ||
          "Media data unavailable";
      }
    }

    bindTopMediaTabs();
    bindElectionCoverageModal(model);
    bindTopicCoverageModal(model, agendaModel);
    window.France2027TopicCoverageModal
      ?.reconcileReturnFocus?.();
  }

  function resolveSignalViewFromHash() {
    const view = hashToView.get(window.location.hash);
    if (view) return view;
    window.history.replaceState(
      null,
      "",
      views[defaultView].hash
    );
    return defaultView;
  }

  function renderAll(event = null) {
    try {
      state.activeView = resolveSignalViewFromHash();
      const models = buildAllViewModels();
      const datasetLane = event?.detail?.name || "";

      if (!datasetLane || datasetLane === "news") {
        renderTopMediaPulse(models.media, models.agenda);
      }

      mount.innerHTML =
        renderFocusWorkspace(models);
        renderCandidateSignalsPanel();

      bindInteractions();
      setActiveSignalView(state.activeView);
    } catch (error) {
      console.error(
        "Hybrid Signal Board render failed",
        error
      );

      mount.innerHTML =
        `<div class="hybrid-state is-error" role="alert">The analytical workspace could not render. Existing dashboard evidence remains available below.</div>`;

      if (topMediaMount) {
        topMediaMount.innerHTML =
          `<div class="hybrid-state is-error" role="alert">Media Pulse could not render.</div>`;
      }

      if (topMediaMetrics) {
        topMediaMetrics.textContent =
          "Media Pulse unavailable";
      }
    }
  }

  function handleSignalHashChange() {
    const next = resolveSignalViewFromHash();
    const shouldScroll = state.scrollOnNextHash;
    state.scrollOnNextHash = false;
    setActiveSignalView(next, { scrollWorkspace: shouldScroll });
  }

  function retainLegacyComparison() {
    const legacy = document.querySelector(".intelligence-grid");
    const polling = document.getElementById("polling-evidence-lab");
    if (!legacy || !polling || legacy.closest(".hybrid-legacy")) return;
    const details = document.createElement("details");
    details.className = "hybrid-legacy";
    const summary = document.createElement("summary");
    summary.textContent = "Legacy middle layout — comparison only";
    details.append(summary, legacy);
    polling.insertAdjacentElement("afterend", details);
  }

  loadRunoffArchive();
  retainLegacyComparison();
  renderAll();
  window.addEventListener("hashchange", handleSignalHashChange);
  document.addEventListener("hybrid:dataset", renderAll);

  window.hybridDashboard = Object.freeze({
    isValidRunoffArchivePayload,
    loadRunoffArchive,
    buildRunoffArchiveModel,
    groupRunoffHistoryWindows,
    buildMediaCandidateCanonicalizer,
    deriveCandidateVisibility,
    isValidCandidateVisibility,
    resolveCandidateVisibility,
    deriveAcceptedNewsPublisherMetric,
    buildRunoffViewModel,
    buildMediaViewModel,
    buildAgendaViewModel,
    buildClaimsViewModel,
    renderSummaryGrid,
    renderRunoffSummary,
    renderMediaSummary,
    renderAgendaSummary,
    renderClaimsSummary,
    renderFocusWorkspace,
    renderRunoffPanel,
    renderMediaPanel,
    renderAgendaPanel,
    renderClaimsPanel,
    setActiveSignalView,
    handleSignalHashChange
  });
})();
