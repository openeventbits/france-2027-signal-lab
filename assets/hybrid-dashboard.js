(() => {
  "use strict";


  const translate = (key, fallback, parameters) => {
    const localizer = globalThis.FR27I18N;

    return localizer && typeof localizer.t === "function"
      ? localizer.t(key, parameters)
      : fallback;
  };

  const renderStrongDateOrUnavailable = (
    value,
    options,
    fallbackFormatter
  ) => {
    const localizer = globalThis.FR27I18N;
    const renderedValue = value
      ? localizer &&
        typeof localizer.formatDate === "function"
        ? localizer.formatDate(value, options)
        : fallbackFormatter()
      : translate(
          "coverage_modal.unavailable",
          "Unavailable"
        );

    return `<strong>${escapeHtml(renderedValue)}</strong>`;
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
    candidates: {
      label: translate("signal_board.candidates_847367c6", "CANDIDATES"),
      title: translate("signal_board.candidate_signals", "Candidate Signals"),
      hash: "#signal-candidates",
      tabId: "signal-candidates-tab",
      panelId: "signal-candidates-panel"
    },
    agenda: {
      label: "AGENDA",
      title: translate("signal_board.campaign_agenda", "Campaign Agenda"),
      hash: "#signal-agenda",
      tabId: "signal-agenda-tab",
      panelId: "signal-agenda-panel",
      index: "3"
    },
    events: {
      label: "EVENTS",
      title: translate("signal_board.campaign_events", "Campaign Events"),
      hash: "#signal-events",
      tabId: "signal-events-tab",
      panelId: "signal-events-panel"
    },
    issues: {
      label: "ISSUES",
      title: "Policy Issues",
      hash: "#signal-issues",
      tabId: "signal-issues-tab",
      panelId: "signal-issues-panel"
    },
    runoff: {
      label: translate("signal_board.runoff", "RUNOFF"),
      title: translate("signal_board.closest_runoff", "Closest Runoff"),
      hash: "#signal-runoff",
      tabId: "signal-runoff-tab",
      panelId: "signal-runoff-panel",
      index: "1"
    },
  });
  const viewOrder = Object.keys(views);
  const hashToView = new Map(viewOrder.map(key => [views[key].hash, key]));
  const defaultView = "candidates";
  const state = {
    activeView: hashToView.get(window.location.hash) || defaultView,
    selectedRunoffHistoryKey: "",
    selectedAgendaTopicId: "",
    selectedPolicyIssueId: "",
    selectedCampaignEventId: "",
    selectedCampaignEventWeekStart: "",
    campaignEventTypeFilter: "all",
    selectedCandidateSignalsId: null,
    candidateSignals: {
      status: "loading",
      candidates: [],
      metadata: {},
      reason: null
    },
    candidateAttention: {
      status: "loading",
      payload: null,
      reason: null
    },
    candidateVisibilityHistory: {
      status: "loading",
      payload: null,
      reason: null
    },
    candidateAgendaHistory: {
      status: "loading",
      payload: null,
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
  let candidateScrutinyPopover = null;
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


  const candidateAttentionRequest =
    window.France2027CandidateAttention
      ?.load("candidate_attention.json")
      .then(candidateAttentionState => {
        state.candidateAttention =
          candidateAttentionState;
        renderCandidateSignalsPanel();
        return candidateAttentionState;
      })
      .catch(() => {
        const candidateAttentionState = {
          status: "unavailable",
          payload: null,
          reason: "fetch_failed"
        };

        state.candidateAttention =
          candidateAttentionState;

        renderCandidateSignalsPanel();

        return candidateAttentionState;
      });

  const candidateVisibilityHistoryRequest =
    Promise.resolve(candidateSignalsRequest)
      .then(candidateSignalsState => {
        if (
          candidateSignalsState?.status !== "ready" ||
          !Array.isArray(candidateSignalsState.candidates) ||
          !candidateSignalsState.candidates.length
        ) {
          return {
            status: "unavailable",
            payload: null,
            reason: "candidate_signals_unavailable"
          };
        }

        const loader =
          window.France2027CandidateVisibilityHistory;

        if (!loader) {
          return {
            status: "unavailable",
            payload: null,
            reason: "history_loader_unavailable"
          };
        }

        return loader.load(
          "candidate_visibility_history.json",
          candidateSignalsState.candidates
        );
      })
      .then(candidateVisibilityHistoryState => {
        state.candidateVisibilityHistory =
          candidateVisibilityHistoryState;

        renderCandidateSignalsPanel();

        return candidateVisibilityHistoryState;
      })
      .catch(() => {
        const candidateVisibilityHistoryState = {
          status: "unavailable",
          payload: null,
          reason: "fetch_failed"
        };

        state.candidateVisibilityHistory =
          candidateVisibilityHistoryState;

        renderCandidateSignalsPanel();

        return candidateVisibilityHistoryState;
      });

  const candidateAgendaHistoryRequest =
    Promise.resolve()
      .then(() => {
        const loader =
          window.France2027CandidateAgendaHistory;

        return loader
          ? loader.load("candidate_agenda_history.json")
          : {
            status: "unavailable",
            payload: null,
            reason: "history_loader_unavailable"
          };
      })
      .then(candidateAgendaHistoryState => {
        state.candidateAgendaHistory =
          candidateAgendaHistoryState;
        renderCandidateSignalsPanel();
        return candidateAgendaHistoryState;
      })
      .catch(() => {
        const candidateAgendaHistoryState = {
          status: "unavailable",
          payload: null,
          reason: "fetch_failed"
        };
        state.candidateAgendaHistory =
          candidateAgendaHistoryState;
        renderCandidateSignalsPanel();
        return candidateAgendaHistoryState;
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

    const rawAgendaTopics =
      Array.isArray(
        payload.campaign_agenda
          ?.topics
      )
        ? payload.campaign_agenda
            .topics
        : [];

    const agendaTopics =
      isValidAgendaBaseTopics(
        rawAgendaTopics
      )
        ? rawAgendaTopics.filter(
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
  const AGENDA_MOVEMENT_SHARE_THRESHOLD_PP = 5;
  const AGENDA_MOVEMENT_SOURCE_DAY_DELTA_MIN = 2;
  const AGENDA_MOVEMENT_COMPARISON_ACTIVITY_MIN = 5;

  const AGENDA_EVENT_DRIVEN_PEAK_SHARE_MIN = 0.40;
  const AGENDA_EVENT_DRIVEN_SOURCE_DAYS_MIN = 5;
  const AGENDA_PERSISTENT_ACTIVE_14_MIN = 7;
  const AGENDA_PERSISTENT_ACTIVE_30_MIN = 12;

  function agendaMovementLabel(
    latestSourceDays,
    previousSourceDays,
    agendaShareChangePp
  ) {
    const latest = number(latestSourceDays);
    const previous = number(previousSourceDays);
    const change = number(agendaShareChangePp);
    const sourceDayDelta = latest - previous;
    const comparisonActivity = latest + previous;

    if (
      comparisonActivity >= AGENDA_MOVEMENT_COMPARISON_ACTIVITY_MIN &&
      change >= AGENDA_MOVEMENT_SHARE_THRESHOLD_PP &&
      sourceDayDelta >= AGENDA_MOVEMENT_SOURCE_DAY_DELTA_MIN
    ) {
      return "RISING";
    }

    if (
      comparisonActivity >= AGENDA_MOVEMENT_COMPARISON_ACTIVITY_MIN &&
      change <= -AGENDA_MOVEMENT_SHARE_THRESHOLD_PP &&
      sourceDayDelta <= -AGENDA_MOVEMENT_SOURCE_DAY_DELTA_MIN
    ) {
      return "FADING";
    }

    return "STABLE";
  }

  function agendaStructureLabel(
    activeDays14,
    activeDays30,
    peakDayShare,
    sourceDayCount
  ) {
    if (
      number(sourceDayCount) >= AGENDA_EVENT_DRIVEN_SOURCE_DAYS_MIN &&
      number(peakDayShare) >= AGENDA_EVENT_DRIVEN_PEAK_SHARE_MIN
    ) {
      return "EVENT-DRIVEN";
    }

    if (
      number(activeDays14) >= AGENDA_PERSISTENT_ACTIVE_14_MIN ||
      number(activeDays30) >= AGENDA_PERSISTENT_ACTIVE_30_MIN
    ) {
      return "PERSISTENT";
    }

    return "INTERMITTENT";
  }

  function agendaSourceDaysInRange(
    dailyActivity,
    startDate,
    endDate
  ) {
    return dailyActivity.reduce(
      (total, day) =>
        day.date >= startDate && day.date <= endDate
          ? total + number(day.source_day_count)
          : total,
      0
    );
  }

  function agendaEvolutionTopicModel(
    topic,
    legacyTopic,
    evolution
  ) {
    const dailyActivity = Array.isArray(topic.daily_activity)
      ? topic.daily_activity
      : [];

    const bins = Array.from(
      { length: 6 },
      (_, index) => {
        const days = dailyActivity.slice(
          index * 5,
          index * 5 + 5
        );

        return {
          start: days[0]?.date || "",
          end: days[days.length - 1]?.date || "",
          sourceDays: days.reduce(
            (total, day) =>
              total + number(day.source_day_count),
            0
          )
        };
      }
    );

    const latestSourceDays = agendaSourceDaysInRange(
      dailyActivity,
      evolution.latest_start,
      evolution.latest_end
    );

    const previousSourceDays = agendaSourceDaysInRange(
      dailyActivity,
      evolution.previous_start,
      evolution.previous_end
    );

    const completeDays = dailyActivity.filter(
      day => day.date <= evolution.latest_end
    );

    const latest14 = completeDays.slice(-14);

    const activeDays14 = latest14.reduce(
      (total, day) =>
        total + (number(day.item_count) > 0 ? 1 : 0),
      0
    );

    let peakDay = null;

    dailyActivity.forEach(day => {
      if (
        peakDay === null ||
        number(day.source_day_count) >
          number(peakDay.source_day_count)
      ) {
        peakDay = day;
      }
    });

    const sourceDayCount = number(
      topic.source_day_count
    );

    const peakDayShare = (
      sourceDayCount > 0 && peakDay
        ? number(peakDay.source_day_count) /
          sourceDayCount
        : 0
    );

    return {
      ...topic,
      supporting_items:
        Array.isArray(legacyTopic?.supporting_items)
          ? legacyTopic.supporting_items
          : [],
      publisher_names:
        Array.isArray(legacyTopic?.publisher_names)
          ? legacyTopic.publisher_names
          : [],
      legacySourceDayCount:
        number(legacyTopic?.source_day_count),
      bins,
      latestSourceDays,
      previousSourceDays,
      activeDays14,
      peakDayDate: peakDay?.date || "",
      peakDaySourceDays:
        number(peakDay?.source_day_count),
      peakDayShare,
      structure: agendaStructureLabel(
        activeDays14,
        number(topic.active_day_count),
        peakDayShare,
        sourceDayCount
      ),
      associatedSignals:
        Array.isArray(topic.matched_term_counts)
          ? topic.matched_term_counts.slice()
          : []
    };
  }

  function agendaRankByWindow(
    topics,
    field
  ) {
    return [...topics].sort(
      (a, b) =>
        number(b[field]) - number(a[field]) ||
        a.label.localeCompare(b.label, "en")
    );
  }

  function isAgendaNonNegativeInteger(value) {
    return Number.isInteger(value) && value >= 0;
  }

  function isValidAgendaBaseTopics(topics) {
    if (!Array.isArray(topics)) return false;

    const topicIds = new Set();

    return topics.every(topic => {
      if (
        !topic ||
        typeof topic !== "object" ||
        typeof topic.id !== "string" ||
        !topic.id ||
        topicIds.has(topic.id) ||
        typeof topic.label !== "string" ||
        !topic.label ||
        !isAgendaNonNegativeInteger(topic.item_count) ||
        !isAgendaNonNegativeInteger(topic.publisher_count) ||
        !isAgendaNonNegativeInteger(topic.source_day_count) ||
        !isAgendaNonNegativeInteger(topic.active_day_count) ||
        typeof topic.display_eligible !== "boolean" ||
        !isAgendaNonNegativeInteger(topic.supporting_item_count) ||
        !isAgendaNonNegativeInteger(topic.omitted_item_count) ||
        !Array.isArray(topic.publisher_names) ||
        !Array.isArray(topic.supporting_items)
      ) {
        return false;
      }

      topicIds.add(topic.id);
      return true;
    });
  }

  function agendaDateValue(dateKey) {
    if (
      typeof dateKey !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(dateKey)
    ) {
      return null;
    }

    const value = new Date(`${dateKey}T00:00:00Z`);

    if (
      Number.isNaN(value.getTime()) ||
      value.toISOString().slice(0, 10) !== dateKey
    ) {
      return null;
    }

    return value;
  }

  function shiftAgendaDate(dateKey, dayDelta) {
    const value = agendaDateValue(dateKey);
    if (!value) return "";

    value.setUTCDate(value.getUTCDate() + dayDelta);
    return value.toISOString().slice(0, 10);
  }

  function isValidAgendaEvolution(evolution, baseTopics) {
    if (
      !evolution ||
      typeof evolution !== "object" ||
      evolution.period_days !== 30 ||
      evolution.comparison_days !== 7 ||
      typeof evolution.period_end_partial !== "boolean" ||
      !Array.isArray(evolution.topics) ||
      !Array.isArray(baseTopics) ||
      !baseTopics.length
    ) {
      return false;
    }

    const dateFields = [
      "period_start",
      "period_end",
      "latest_start",
      "latest_end",
      "previous_start",
      "previous_end"
    ];

    if (
      dateFields.some(
        field => !agendaDateValue(evolution[field])
      )
    ) {
      return false;
    }

    if (
      shiftAgendaDate(
        evolution.period_start,
        evolution.period_days - 1
      ) !== evolution.period_end ||
      shiftAgendaDate(
        evolution.period_end,
        -1
      ) !== evolution.latest_end ||
      shiftAgendaDate(
        evolution.latest_end,
        -(evolution.comparison_days - 1)
      ) !== evolution.latest_start ||
      shiftAgendaDate(
        evolution.latest_start,
        -1
      ) !== evolution.previous_end ||
      shiftAgendaDate(
        evolution.previous_end,
        -(evolution.comparison_days - 1)
      ) !== evolution.previous_start
    ) {
      return false;
    }

    const baseById = new Map();

    for (const topic of baseTopics) {
      if (
        !topic ||
        typeof topic.id !== "string" ||
        !topic.id ||
        typeof topic.label !== "string" ||
        !topic.label ||
        baseById.has(topic.id)
      ) {
        return false;
      }

      baseById.set(topic.id, topic);
    }

    if (
      evolution.topics.length !== baseById.size
    ) {
      return false;
    }

    const seenEvolutionIds = new Set();

    for (const topic of evolution.topics) {
      if (
        !topic ||
        typeof topic !== "object" ||
        typeof topic.id !== "string" ||
        !baseById.has(topic.id) ||
        seenEvolutionIds.has(topic.id) ||
        topic.label !== baseById.get(topic.id).label ||
        !isAgendaNonNegativeInteger(topic.item_count) ||
        !isAgendaNonNegativeInteger(topic.publisher_count) ||
        !isAgendaNonNegativeInteger(topic.source_day_count) ||
        !isAgendaNonNegativeInteger(topic.active_day_count) ||
        typeof topic.display_eligible !== "boolean" ||
        !Array.isArray(topic.daily_activity) ||
        topic.daily_activity.length !== evolution.period_days ||
        !Array.isArray(topic.matched_term_counts)
      ) {
        return false;
      }

      let itemTotal = 0;
      let sourceDayTotal = 0;
      let activeDayTotal = 0;

      for (
        let index = 0;
        index < topic.daily_activity.length;
        index += 1
      ) {
        const day = topic.daily_activity[index];
        const expectedDate = shiftAgendaDate(
          evolution.period_start,
          index
        );

        if (
          !day ||
          typeof day !== "object" ||
          day.date !== expectedDate ||
          !isAgendaNonNegativeInteger(day.item_count) ||
          !isAgendaNonNegativeInteger(day.source_day_count) ||
          day.source_day_count > day.item_count
        ) {
          return false;
        }

        itemTotal += day.item_count;
        sourceDayTotal += day.source_day_count;
        activeDayTotal += day.item_count > 0 ? 1 : 0;
      }

      if (
        itemTotal !== topic.item_count ||
        sourceDayTotal !== topic.source_day_count ||
        activeDayTotal !== topic.active_day_count
      ) {
        return false;
      }

      seenEvolutionIds.add(topic.id);
    }

    return seenEvolutionIds.size === baseById.size;
  }


  function policyIssueShortLabel(topic) {
    const labels = {
      economy_public_finances:
        "Economy & finances",
      work_purchasing_power_pensions:
        "Work & pensions",
      immigration_identity_secularism:
        "Immigration & identity",
      security_justice:
        "Security & justice",
      health_education_public_services:
        "Health & education",
      climate_energy_agriculture:
        "Climate & energy",
      europe_defence_foreign_affairs:
        "Europe & defence",
      institutions_democracy_territories:
        "Institutions & territories"
    };

    return (
      labels[topic?.id] ||
      topic?.label ||
      "Issue"
    );
  }

  function policyIssueCode(topic) {
    const labels = {
      economy_public_finances:
        "ECONOMY",
      work_purchasing_power_pensions:
        "WORK & PENSIONS",
      immigration_identity_secularism:
        "IMMIGRATION",
      security_justice:
        "SECURITY",
      health_education_public_services:
        "HEALTH",
      climate_energy_agriculture:
        "CLIMATE",
      europe_defence_foreign_affairs:
        "EUROPE",
      institutions_democracy_territories:
        "INSTITUTIONS"
    };

    return (
      labels[topic?.id] ||
      "ISSUE"
    );
  }

  function policySubtopicLabel(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(
        /\b\w/g,
        character =>
          character.toUpperCase()
      );
  }

  function isValidPolicyAgendaBaseTopics(
    topics
  ) {
    if (!Array.isArray(topics)) {
      return false;
    }

    const ids = new Set();

    return topics.every(topic => {
      if (
        !topic ||
        typeof topic !== "object" ||
        typeof topic.id !== "string" ||
        !topic.id ||
        ids.has(topic.id) ||
        typeof topic.label !== "string" ||
        !topic.label ||
        !isAgendaNonNegativeInteger(
          topic.item_count
        ) ||
        !isAgendaNonNegativeInteger(
          topic.publisher_count
        ) ||
        !isAgendaNonNegativeInteger(
          topic.source_day_count
        ) ||
        !isAgendaNonNegativeInteger(
          topic.active_day_count
        ) ||
        typeof topic.display_eligible !==
          "boolean" ||
        !Array.isArray(
          topic.publisher_names
        ) ||
        !Array.isArray(
          topic.subtopic_counts
        ) ||
        !Array.isArray(
          topic.candidate_counts
        ) ||
        !Array.isArray(
          topic.supporting_items
        ) ||
        !isAgendaNonNegativeInteger(
          topic.supporting_item_count
        ) ||
        !isAgendaNonNegativeInteger(
          topic.omitted_item_count
        )
      ) {
        return false;
      }

      if (
        topic.publisher_count !==
          topic.publisher_names.length ||
        topic.supporting_item_count !==
          topic.supporting_items.length ||
        topic.supporting_item_count >
          topic.item_count ||
        topic.omitted_item_count !==
          topic.item_count -
            topic.supporting_item_count
      ) {
        return false;
      }

      const subtopicIds =
        new Set();

      for (
        const subtopic
        of topic.subtopic_counts
      ) {
        if (
          !subtopic ||
          typeof subtopic !== "object" ||
          typeof subtopic.id !==
            "string" ||
          !subtopic.id ||
          subtopicIds.has(
            subtopic.id
          ) ||
          !isAgendaNonNegativeInteger(
            subtopic.item_count
          ) ||
          subtopic.item_count < 1 ||
          subtopic.item_count >
            topic.item_count
        ) {
          return false;
        }

        subtopicIds.add(
          subtopic.id
        );
      }

      const candidates =
        new Set();

      for (
        const candidate
        of topic.candidate_counts
      ) {
        if (
          !candidate ||
          typeof candidate !==
            "object" ||
          typeof candidate.candidate !==
            "string" ||
          !candidate.candidate ||
          candidates.has(
            candidate.candidate
          ) ||
          !isAgendaNonNegativeInteger(
            candidate.item_count
          ) ||
          candidate.item_count < 1 ||
          candidate.item_count >
            topic.item_count
        ) {
          return false;
        }

        candidates.add(
          candidate.candidate
        );
      }

      ids.add(topic.id);
      return true;
    });
  }

  function isValidPolicyAgendaEvolution(
    evolution,
    baseTopics
  ) {
    if (
      !isValidAgendaEvolution(
        evolution,
        baseTopics
      ) ||
      !Array.isArray(
        evolution
          ?.accepted_daily_activity
      ) ||
      evolution
        .accepted_daily_activity
        .length !==
        evolution.period_days
    ) {
      return false;
    }

    for (
      let index = 0;
      index <
        evolution
          .accepted_daily_activity
          .length;
      index += 1
    ) {
      const day =
        evolution
          .accepted_daily_activity[
            index
          ];

      if (
        !day ||
        typeof day !== "object" ||
        day.date !==
          shiftAgendaDate(
            evolution.period_start,
            index
          ) ||
        !isAgendaNonNegativeInteger(
          day.source_day_count
        )
      ) {
        return false;
      }
    }

    for (
      const topic
      of evolution.topics
    ) {
      if (
        !isAgendaNonNegativeInteger(
          topic
            .latest_source_day_count
        ) ||
        !isAgendaNonNegativeInteger(
          topic
            .previous_source_day_count
        ) ||
        !Number.isFinite(
          Number(
            topic.latest_incidence
          )
        ) ||
        !Number.isFinite(
          Number(
            topic.previous_incidence
          )
        ) ||
        !Number.isFinite(
          Number(
            topic.incidence_change_pp
          )
        ) ||
        number(
          topic.latest_incidence
        ) < 0 ||
        number(
          topic.latest_incidence
        ) > 1 ||
        number(
          topic.previous_incidence
        ) < 0 ||
        number(
          topic.previous_incidence
        ) > 1
      ) {
        return false;
      }

      for (
        const day
        of topic.daily_activity
      ) {
        if (
          !isAgendaNonNegativeInteger(
            day
              .accepted_source_day_count
          ) ||
          !Number.isFinite(
            Number(day.incidence)
          ) ||
          number(day.incidence) < 0 ||
          number(day.incidence) > 1 ||
          number(
            day.source_day_count
          ) >
            number(
              day
                .accepted_source_day_count
            )
        ) {
          return false;
        }
      }
    }

    return true;
  }

  function buildPolicyAgendaViewModel() {
    const unavailable =
      viewModelState("news");

    if (unavailable) {
      return {
        domain: "issues",
        ...unavailable
      };
    }

    const agenda =
      dashboardState.news
        ?.policy_agenda;

    if (
      !agenda ||
      typeof agenda !== "object"
    ) {
      return {
        domain: "issues",
        state: "unavailable",
        message:
          "Policy Issues are not available in the current news artifact."
      };
    }

    const allTopics =
      Array.isArray(agenda.topics)
        ? agenda.topics
        : [];

    if (
      agenda.method !==
        "accepted_relevant_news_by_policy_issue_multilabel" ||
      !isAgendaNonNegativeInteger(
        agenda.input_item_count
      ) ||
      !isAgendaNonNegativeInteger(
        agenda.classified_item_count
      ) ||
      !isAgendaNonNegativeInteger(
        agenda.unclassified_item_count
      ) ||
      !isAgendaNonNegativeInteger(
        agenda.label_assignment_count
      ) ||
      agenda.classified_item_count +
        agenda.unclassified_item_count !==
        agenda.input_item_count ||
      agenda.label_assignment_count <
        agenda.classified_item_count ||
      !isValidPolicyAgendaBaseTopics(
        allTopics
      )
    ) {
      return {
        domain: "issues",
        state: "invalid",
        message:
          "Policy Issues are unavailable because the policy contract is malformed."
      };
    }

    const assignmentTotal =
      allTopics.reduce(
        (total, topic) =>
          total +
          number(
            topic.item_count
          ),
        0
      );

    if (
      assignmentTotal !==
      agenda.label_assignment_count
    ) {
      return {
        domain: "issues",
        state: "invalid",
        message:
          "Policy Issues are unavailable because multi-label assignment totals are inconsistent."
      };
    }

    const eligible =
      [...allTopics]
        .filter(
          topic =>
            topic.display_eligible
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
              b.item_count
            ) -
              number(
                a.item_count
              ) ||
            a.label.localeCompare(
              b.label,
              "en"
            )
        );

    if (!eligible.length) {
      state.selectedPolicyIssueId =
        "";

      return {
        domain: "issues",
        state: "empty",
        message:
          "No policy issue currently meets the publication threshold.",
        topics: [],
        selectedIssue: null,
        evolutionReady: false
      };
    }

    const evolution =
      agenda.evolution;

    if (
      !isValidPolicyAgendaEvolution(
        evolution,
        allTopics
      )
    ) {
      return {
        domain: "issues",
        state: "invalid",
        message:
          "Policy Issues are unavailable because the evolution contract is malformed."
      };
    }

    const baseById =
      new Map(
        allTopics.map(
          topic => [
            topic.id,
            topic
          ]
        )
      );

    let evolutionTopics =
      evolution.topics
        .filter(
          topic =>
            topic.display_eligible
        )
        .map(topic => {
          const base =
            baseById.get(
              topic.id
            );

          const modeled =
            agendaEvolutionTopicModel(
              topic,
              base,
              evolution
            );

          const changePp =
            number(
              topic
                .incidence_change_pp
            );

          return {
            ...modeled,

            subtopic_counts:
              base
                .subtopic_counts
                .slice(),

            candidate_counts:
              base
                .candidate_counts
                .slice(),

            latestIncidence:
              number(
                topic
                  .latest_incidence
              ) * 100,

            previousIncidence:
              number(
                topic
                  .previous_incidence
              ) * 100,

            incidenceChangePp:
              changePp,

            movement:
              agendaMovementLabel(
                number(
                  topic
                    .latest_source_day_count
                ),
                number(
                  topic
                    .previous_source_day_count
                ),
                changePp
              )
          };
        });

    evolutionTopics.sort(
      (a, b) =>
        number(
          b.source_day_count
        ) -
          number(
            a.source_day_count
          ) ||
        number(
          b.item_count
        ) -
          number(
            a.item_count
          ) ||
        a.label.localeCompare(
          b.label,
          "en"
        )
    );

    if (
      !evolutionTopics.some(
        topic =>
          topic.id ===
          state
            .selectedPolicyIssueId
      )
    ) {
      state.selectedPolicyIssueId =
        evolutionTopics[0]
          ?.id || "";
    }

    const selectedIssue =
      evolutionTopics.find(
        topic =>
          topic.id ===
          state
            .selectedPolicyIssueId
      ) ||
      evolutionTopics[0] ||
      null;

    const latestRanked =
      [...evolutionTopics]
        .sort(
          (a, b) =>
            number(
              b.latestIncidence
            ) -
              number(
                a.latestIncidence
              ) ||
            number(
              b.latestSourceDays
            ) -
              number(
                a.latestSourceDays
              ) ||
            a.label.localeCompare(
              b.label,
              "en"
            )
        );

    const leadingIssue =
      latestRanked[0] ||
      null;

    const policyCoverage =
      agenda.input_item_count
        ? (
            agenda
              .classified_item_count /
            agenda
              .input_item_count
          ) * 100
        : 0;

    const diagnostics = {
      activeIssues:
        evolutionTopics.filter(
          topic =>
            number(
              topic.latestSourceDays
            ) > 0
        ).length,

      leadingIssue,

      risingIssues:
        evolutionTopics.filter(
          topic =>
            topic.movement ===
            "RISING"
        ).length,

      policyCoverage
    };

    const evolutionBins =
      evolutionTopics[0]
        ?.bins
        ?.map(bin => ({
          start: bin.start,
          end: bin.end
        })) || [];

    const heatmapMaxSourceDays =
      Math.max(
        1,
        ...evolutionTopics
          .flatMap(
            topic =>
              topic.daily_activity
                .map(
                  day =>
                    number(
                      day
                        .source_day_count
                    )
                )
          )
      );

    return {
      domain: "issues",
      state: "ready",
      topics:
        evolutionTopics,
      selectedIssue,
      evolutionReady: true,
      evolution,
      diagnostics,
      evolutionBins,
      heatmapMaxSourceDays,

      inputItemCount:
        number(
          agenda.input_item_count
        ),

      classifiedItemCount:
        number(
          agenda
            .classified_item_count
        ),

      assignmentCount:
        number(
          agenda
            .label_assignment_count
        ),

      displayMinimum:
        number(
          agenda
            .display_min_source_days
        ),

      generatedAt:
        dashboardState
          .news
          .generated_at
    };
  }

  function buildAgendaViewModel() {
    const unavailable = viewModelState("news");
    if (unavailable) return { domain: "agenda", ...unavailable };

    const agenda = dashboardState.news.campaign_agenda;
    const allTopics = Array.isArray(agenda?.topics) ? agenda.topics : [];

    if (!isValidAgendaBaseTopics(allTopics)) {
      return {
        domain: "agenda",
        state: "invalid",
        message: "Campaign Agenda is unavailable because its topic contract is malformed."
      };
    }

    /*
     * Keep the legacy topic collection unchanged here.
     * Media Pulse already consumes Agenda model topics, so the
     * new calendar-day projection must not silently redefine
     * existing Media Pulse values.
     */
    const sorted = [...allTopics].sort((a, b) =>
      number(b.source_day_count) - number(a.source_day_count) ||
      number(b.item_count) - number(a.item_count) ||
      a.label.localeCompare(b.label, "en")
    );

    const eligible = sorted.filter(
      topic => topic.display_eligible
    );

    const selectable = eligible;

    if (
      !selectable.some(
        topic =>
          topic.id === state.selectedAgendaTopicId
      )
    ) {
      state.selectedAgendaTopicId =
        selectable[0]?.id || "";
    }

    const selectedTopic =
      selectable.find(
        topic =>
          topic.id === state.selectedAgendaTopicId
      ) ||
      selectable[0] ||
      null;

    const evolution = agenda?.evolution;

    const rawEvolutionTopics =
      Array.isArray(evolution?.topics)
        ? evolution.topics
        : [];

    const evolutionReady =
      isValidAgendaEvolution(
        evolution,
        allTopics
      );

    const baseModel = {
      domain: "agenda",
      state: selectable.length
        ? "ready"
        : "empty",
      topics: selectable,
      eligibleTopics: eligible,
      selectedTopic,
      maxSourceDays: Math.max(
        1,
        ...selectable.map(
          topic => number(topic.source_day_count)
        )
      ),
      displayMinimum:
        number(agenda?.display_min_source_days),
      inputItemCount:
        number(agenda?.input_item_count),
      windowDays:
        number(
          agenda?.window_days ||
          dashboardState.news.window_days
        ),
      method: agenda?.method || "",
      generatedAt:
        dashboardState.news.generated_at,
      evolutionReady: false,
      evolutionTopics: [],
      selectedEvolutionTopic: null,
      evolutionBins: [],
      heatmapMaxSourceDays: 1,
      diagnostics: null,
      transitions: []
    };

    if (!evolutionReady) {
      return baseModel;
    }

    const legacyById = new Map(
      allTopics.map(
        topic => [topic.id, topic]
      )
    );

    let evolutionTopics =
      rawEvolutionTopics.map(
        topic =>
          agendaEvolutionTopicModel(
            topic,
            legacyById.get(topic.id),
            evolution
          )
      );

    const evolutionEligible =
      evolutionTopics.filter(
        topic => topic.display_eligible
      );

    evolutionTopics = evolutionEligible;

    if (!evolutionTopics.length) {
      return baseModel;
    }

    const latestDenominator =
      evolutionTopics.reduce(
        (total, topic) =>
          total +
          number(topic.latestSourceDays),
        0
      );

    const previousDenominator =
      evolutionTopics.reduce(
        (total, topic) =>
          total +
          number(topic.previousSourceDays),
        0
      );

    evolutionTopics =
      evolutionTopics.map(topic => {
        const latestAgendaShare =
          latestDenominator
            ? (
                number(topic.latestSourceDays) /
                latestDenominator
              ) * 100
            : 0;

        const previousAgendaShare =
          previousDenominator
            ? (
                number(topic.previousSourceDays) /
                previousDenominator
              ) * 100
            : 0;

        const agendaShareChangePp =
          latestAgendaShare -
          previousAgendaShare;

        return {
          ...topic,
          latestAgendaShare,
          previousAgendaShare,
          agendaShareChangePp,
          movement: agendaMovementLabel(
            topic.latestSourceDays,
            topic.previousSourceDays,
            agendaShareChangePp
          )
        };
      });

    evolutionTopics.sort(
      (a, b) =>
        number(b.source_day_count) -
          number(a.source_day_count) ||
        number(b.item_count) -
          number(a.item_count) ||
        a.label.localeCompare(
          b.label,
          "en"
        )
    );

    const selectedEvolutionTopic =
      evolutionTopics.find(
        topic =>
          topic.id === state.selectedAgendaTopicId
      ) ||
      evolutionTopics[0] ||
      null;

    const latestRanked =
      agendaRankByWindow(
        evolutionTopics,
        "latestSourceDays"
      );

    const previousRanked =
      agendaRankByWindow(
        evolutionTopics,
        "previousSourceDays"
      );

    const topCount = Math.min(
      3,
      evolutionTopics.length
    );

    const latestTop = latestRanked
      .slice(0, topCount)
      .map(topic => topic.id);

    const previousTop = new Set(
      previousRanked
        .slice(0, topCount)
        .map(topic => topic.id)
    );

    const top3Turnover =
      latestTop.filter(
        topicId =>
          !previousTop.has(topicId)
      ).length;

    const top3Share = latestRanked
      .slice(0, topCount)
      .reduce(
        (total, topic) =>
          total +
          number(topic.latestAgendaShare),
        0
      );

    const diagnostics = {
      activeTopics:
        evolutionTopics.filter(
          topic =>
            number(topic.latestSourceDays) > 0
        ).length,
      top3Share,
      risingTopics:
        evolutionTopics.filter(
          topic =>
            topic.movement === "RISING"
        ).length,
      top3Turnover,
      top3TurnoverDenominator: topCount,
      latestDenominator,
      previousDenominator
    };

    const transitions =
      evolutionTopics
        .filter(
          topic =>
            topic.movement !== "STABLE"
        )
        .sort(
          (a, b) =>
            Math.abs(
              number(
                b.agendaShareChangePp
              )
            ) -
              Math.abs(
                number(
                  a.agendaShareChangePp
                )
              ) ||
            a.label.localeCompare(
              b.label,
              "en"
            )
        )
        .slice(0, 5)
        .map(topic => ({
          date: evolution.latest_end,
          topicId: topic.id,
          label: topic.label,
          movement: topic.movement,
          agendaShareChangePp:
            topic.agendaShareChangePp,
          latestSourceDays:
            topic.latestSourceDays,
          previousSourceDays:
            topic.previousSourceDays
        }));

    const evolutionBins =
      evolutionTopics[0]?.bins?.map(
        bin => ({
          start: bin.start,
          end: bin.end
        })
      ) || [];

    const heatmapMaxSourceDays = Math.max(
      1,
      ...evolutionTopics.flatMap(topic =>
        (Array.isArray(topic.daily_activity)
          ? topic.daily_activity
          : []
        ).map(day => number(day.source_day_count))
      )
    );

    return {
      ...baseModel,
      evolutionReady: true,
      evolution,
      evolutionTopics,
      selectedEvolutionTopic,
      evolutionBins,
      heatmapMaxSourceDays,
      diagnostics,
      transitions
    };
  }

  function parisTodayKey(now = new Date()) {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat(
        "en-GB",
        {
          timeZone: "Europe/Paris",
          year: "numeric",
          month: "2-digit",
          day: "2-digit"
        }
      )
        .formatToParts(now)
        .filter(part =>
          ["year", "month", "day"].includes(part.type)
        )
        .map(part => [part.type, part.value])
    );

    return `${parts.year}-${parts.month}-${parts.day}`;
  }

  function campaignEventDateKey(event) {
    return String(event?.scheduled_start || "").slice(0, 10);
  }

  function campaignEventDateFromKey(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    if (!match) return null;
    const date = new Date(Date.UTC(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3])
    ));
    return date.getUTCFullYear() === Number(match[1]) &&
      date.getUTCMonth() === Number(match[2]) - 1 &&
      date.getUTCDate() === Number(match[3])
      ? date
      : null;
  }

  function campaignEventOffsetDateKey(value, offsetDays) {
    const date = campaignEventDateFromKey(value);
    if (!date) return "";
    date.setUTCDate(date.getUTCDate() + offsetDays);
    return utcDateKey(date);
  }

  function campaignEventWeekStartKey(value) {
    const date = campaignEventDateFromKey(value);
    if (!date) return value;
    const mondayOffset = (date.getUTCDay() + 6) % 7;
    date.setUTCDate(date.getUTCDate() - mondayOffset);
    return utcDateKey(date);
  }

  function campaignEventMonthShort(value) {
    const date = campaignEventDateFromKey(value);
    if (!date) return "";
    return [
      "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
      "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"
    ][date.getUTCMonth()];
  }

  function campaignEventMonthLong(value) {
    const date = campaignEventDateFromKey(value);
    if (!date) return "";
    return [
      "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
      "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"
    ][date.getUTCMonth()];
  }

  function campaignEventWeekRangeLabel(startKey, endKey) {
    const start = campaignEventDateFromKey(startKey);
    const end = campaignEventDateFromKey(endKey);
    if (!start || !end) return "";
    const startDay = start.getUTCDate();
    const endDay = end.getUTCDate();
    const startMonth = campaignEventMonthShort(startKey);
    const endMonth = campaignEventMonthShort(endKey);
    if (start.getUTCMonth() === end.getUTCMonth()) {
      return `${startDay}–${endDay} ${endMonth}`;
    }
    return `${startDay} ${startMonth}–${endDay} ${endMonth}`;
  }

  const campaignEventTypeOrder = new Map([
    "rally",
    "public_meeting",
    "debate",
    "candidate_visit",
    "campaign_launch",
    "other",
    "sponsorship_deadline",
    "official_candidate_list",
    "campaign_period_boundary",
    "first_round",
    "second_round"
  ].map((value, index) => [value, index]));

  function compareCampaignEvents(left, right, dateDirection = 1) {
    const leftDate = campaignEventDateKey(left);
    const rightDate = campaignEventDateKey(right);
    const dateComparison = leftDate.localeCompare(rightDate);
    if (dateComparison) return dateComparison * dateDirection;

    const leftPrecision = left.time_precision === "datetime" ? 0 : 1;
    const rightPrecision = right.time_precision === "datetime" ? 0 : 1;
    if (leftPrecision !== rightPrecision) {
      return leftPrecision - rightPrecision;
    }

    const timeComparison = String(left.scheduled_start).slice(11, 19)
      .localeCompare(String(right.scheduled_start).slice(11, 19));
    if (timeComparison) return timeComparison * dateDirection;

    const typeComparison =
      (campaignEventTypeOrder.get(left.event_type) ?? Number.MAX_SAFE_INTEGER) -
      (campaignEventTypeOrder.get(right.event_type) ?? Number.MAX_SAFE_INTEGER);
    if (typeComparison) return typeComparison;

    const candidateComparison = (Array.isArray(left.candidate_ids)
      ? left.candidate_ids.join("\u0000")
      : ""
    ).localeCompare(
      Array.isArray(right.candidate_ids)
        ? right.candidate_ids.join("\u0000")
        : ""
    );
    if (candidateComparison) return candidateComparison;

    return String(left.event_key || "").localeCompare(
      String(right.event_key || "")
    ) || String(left.event_id || "").localeCompare(
      String(right.event_id || "")
    );
  }

  function buildCampaignEventHorizon(upcomingEvents, todayKey, weekCount = 12) {
    const horizonStartKey = campaignEventWeekStartKey(todayKey);
    const horizonDays = weekCount * 7;
    const horizonEndKey = campaignEventOffsetDateKey(
      horizonStartKey,
      horizonDays - 1
    );

    const rawHorizonEvents = upcomingEvents.filter(event => {
      const dateKey = campaignEventDateKey(event);
      return dateKey >= todayKey && dateKey <= horizonEndKey;
    });
    const eventsByWeek = new Map();
    rawHorizonEvents.forEach(event => {
      const weekStartKey = campaignEventWeekStartKey(
        campaignEventDateKey(event)
      );
      if (!eventsByWeek.has(weekStartKey)) {
        eventsByWeek.set(weekStartKey, []);
      }
      eventsByWeek.get(weekStartKey).push(event);
    });

    const weekBins = Array.from({ length: weekCount }, (_, index) => {
      const startKey = campaignEventOffsetDateKey(
        horizonStartKey,
        index * 7
      );
      const endKey = campaignEventOffsetDateKey(startKey, 6);
      const events = (eventsByWeek.get(startKey) || [])
        .slice()
        .sort(compareCampaignEvents);
      return {
        index,
        startKey,
        endKey,
        label: campaignEventWeekRangeLabel(startKey, endKey),
        count: events.length,
        events
      };
    });

    const events = [];
    weekBins.forEach(bin => {
      bin.events.forEach((event, laneIndex) => {
        const candidateNames = Array.isArray(event.candidate_names)
          ? event.candidate_names.filter(Boolean)
          : [];
        events.push({
          ...event,
          stripWeekIndex: bin.index,
          stripLane: laneIndex % 3,
          participantCount: candidateNames.length ||
            (Array.isArray(event.participants)
              ? event.participants.filter(Boolean).length
              : 0),
          isMultiCandidate: candidateNames.length > 1
        });
      });
    });

    const monthGroups = [];
    weekBins.forEach(bin => {
      const midpointKey = campaignEventOffsetDateKey(bin.startKey, 3);
      const label = campaignEventMonthLong(midpointKey);
      const previous = monthGroups[monthGroups.length - 1];
      if (previous && previous.label === label) {
        previous.span += 1;
      } else {
        monthGroups.push({
          label,
          start: bin.index + 1,
          span: 1
        });
      }
    });

    const candidateMap = new Map();
    events.forEach((event, eventIndex) => {
      const ids = Array.isArray(event.candidate_ids)
        ? event.candidate_ids
        : [];
      const names = Array.isArray(event.candidate_names)
        ? event.candidate_names
        : [];
      names.filter(Boolean).forEach((name, nameIndex) => {
        const id = String(ids[nameIndex] || name).trim();
        if (!candidateMap.has(id)) {
          candidateMap.set(id, {
            id,
            name,
            count: 0,
            firstEventIndex: eventIndex,
            markers: []
          });
        }
        const candidate = candidateMap.get(id);
        candidate.count += 1;
        candidate.markers.push(event);
      });
    });

    const namedRows = [...candidateMap.values()].sort((a, b) =>
      b.count - a.count ||
      a.firstEventIndex - b.firstEventIndex ||
      a.name.localeCompare(b.name, "fr")
    );
    const visibleNamedRows = namedRows.slice(0, 8);
    const omittedRows = namedRows.slice(8);
    const matrixRows = visibleNamedRows.map(row => ({
      ...row,
      kind: "candidate"
    }));
    if (omittedRows.length) {
      const omittedIds = new Set(omittedRows.map(row => row.id));
      matrixRows.push({
        id: "other-linked",
        name: `OTHER LINKED · ${omittedRows.length}`,
        kind: "aggregate",
        count: events.filter(event =>
          (event.candidate_ids || []).some(id => omittedIds.has(id))
        ).length,
        markers: events.filter(event =>
          (event.candidate_ids || []).some(id => omittedIds.has(id))
        )
      });
    }

    const typeMap = new Map();
    events.forEach(event => {
      typeMap.set(
        event.event_type,
        (typeMap.get(event.event_type) || 0) + 1
      );
    });
    const eventTypes = [...typeMap.entries()]
      .map(([type, count]) => ({ type, count }))
      .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type));

    return {
      weekCount,
      horizonDays,
      horizonStartKey,
      horizonEndKey,
      events,
      weekBins,
      monthGroups,
      matrixRows,
      linkedCandidateCount: candidateMap.size,
      eventTypes,
      stripLaneCount: Math.max(
        1,
        Math.min(3, ...weekBins.map(bin => Math.max(1, bin.count)))
      )
    };
  }

  function buildEventsViewModel() {
    const unavailable = viewModelState("campaignEvents");
    if (unavailable) {
      return {
        domain: "events",
        ...unavailable
      };
    }

    const payload = dashboardState.campaignEvents;
    const events = Array.isArray(payload?.campaign_events)
      ? payload.campaign_events.slice()
      : [];
    const milestones = Array.isArray(payload?.institutional_milestones)
      ? payload.institutional_milestones.slice()
      : [];
    const watch = Array.isArray(payload?.event_watch)
      ? payload.event_watch.slice()
      : [];

    const todayKey = parisTodayKey();
    const eventById = new Map(
      events.map(event => [event.event_id, event])
    );

    const isActiveUpcoming = event => {
      const dateKey = campaignEventDateKey(event);
      return event.status === "scheduled" && dateKey >= todayKey;
    };

    const activeUpcomingEvents = events
      .filter(isActiveUpcoming)
      .sort(compareCampaignEvents);

    const pastScheduledEvents = events
      .filter(event =>
        event.status === "scheduled" &&
        campaignEventDateKey(event) < todayKey
      )
      .sort((a, b) => compareCampaignEvents(a, b, -1));

    const inactiveEvents = events
      .filter(event => event.status !== "scheduled")
      .sort((a, b) => compareCampaignEvents(a, b, -1));

    const nonActiveEvents = [
      ...pastScheduledEvents,
      ...inactiveEvents
    ].sort((a, b) => compareCampaignEvents(a, b, -1));

    const requestedEventTypeFilter = state.campaignEventTypeFilter || "all";
    const eventTypeFilter = requestedEventTypeFilter === "all" ||
      activeUpcomingEvents.some(event =>
        campaignEventMatchesTypeFilter(event, requestedEventTypeFilter)
      )
      ? requestedEventTypeFilter
      : "all";
    state.campaignEventTypeFilter = eventTypeFilter;
    const filteredUpcomingEvents = activeUpcomingEvents.filter(event =>
      campaignEventMatchesTypeFilter(event, eventTypeFilter)
    );
    const eventWatch = watch
      .map(update => ({
        ...update,
        event: eventById.get(update.event_id) || null
      }))
      .sort((a, b) =>
        String(b.observed_at).localeCompare(String(a.observed_at)) ||
        String(a.update_id).localeCompare(String(b.update_id))
      );

    milestones.sort(compareCampaignEvents);

    const horizon = buildCampaignEventHorizon(
      filteredUpcomingEvents,
      todayKey,
      12
    );

    const requestedSelected = state.selectedCampaignEventId;
    const requestedEvent = eventById.get(requestedSelected) || null;
    const requestedEventMatchesFilter = requestedEvent &&
      (eventTypeFilter === "all" ||
        campaignEventMatchesTypeFilter(requestedEvent, eventTypeFilter));
    const selectedEvent =
      (requestedEventMatchesFilter ? requestedEvent : null) ||
      filteredUpcomingEvents[0] ||
      (eventTypeFilter === "all" ? nonActiveEvents[0] : null) ||
      null;

    state.selectedCampaignEventId = selectedEvent?.event_id || "";

    const selectedUpdates = selectedEvent
      ? eventWatch.filter(update => update.event_id === selectedEvent.event_id)
      : [];

    const selectedEventWeekStart = selectedEvent
      ? campaignEventWeekStartKey(campaignEventDateKey(selectedEvent))
      : "";
    const requestedWeekStart = state.selectedCampaignEventWeekStart;
    const selectedWeek =
      horizon.weekBins.find(bin => bin.startKey === requestedWeekStart) ||
      horizon.weekBins.find(bin => bin.startKey === selectedEventWeekStart) ||
      horizon.weekBins.find(bin => bin.count > 0) ||
      horizon.weekBins[0] ||
      null;

    if (selectedWeek) {
      state.selectedCampaignEventWeekStart = selectedWeek.startKey;
    }

    const next14EndKey = campaignEventOffsetDateKey(todayKey, 13);
    const next14Count = activeUpcomingEvents.filter(event =>
      campaignEventDateKey(event) <= next14EndKey
    ).length;
    const multiCandidateCount = activeUpcomingEvents.filter(event =>
      Array.isArray(event.candidate_names) &&
      event.candidate_names.filter(Boolean).length > 1
    ).length;
    const verifiedCount = activeUpcomingEvents.filter(event =>
      event.evidence_status === "verified"
    ).length;

    const organizationMap = new Map();
    horizon.events.forEach((event, eventIndex) => {
      const name = String(event.organization || "").trim();
      if (!name) return;
      if (!organizationMap.has(name)) {
        organizationMap.set(name, {
          name,
          kind: "organization",
          count: 0,
          firstEventIndex: eventIndex,
          markers: []
        });
      }
      const row = organizationMap.get(name);
      row.count += 1;
      row.markers.push(event);
    });

    const organizationRows = [...organizationMap.values()]
      .sort((a, b) =>
        a.firstEventIndex - b.firstEventIndex ||
        a.name.localeCompare(b.name, "fr")
      );

    return {
      domain: "events",
      state:
        events.length || milestones.length || watch.length
          ? "ready"
          : "empty",
      generatedAt: payload.generated_at,
      dataAsOf: payload.data_as_of,
      todayKey,
      upcomingEvents: activeUpcomingEvents,
      filteredUpcomingEvents,
      eventTypeFilter,
      pastScheduledEvents,
      inactiveEvents,
      nonActiveEvents,
      eventWatch,
      milestones,
      horizon,
      selectedEvent,
      selectedUpdates,
      selectedWeek,
      organizationRows,
      eventCount: events.length,
      upcomingCount: activeUpcomingEvents.length,
      pastCount: pastScheduledEvents.length,
      inactiveCount: inactiveEvents.length,
      watchCount: eventWatch.length,
      milestoneCount: milestones.length,
      next14Count,
      multiCandidateCount,
      verifiedCount
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
      events: safelyBuildViewModel("events", buildEventsViewModel),
      agenda: safelyBuildViewModel("agenda", buildAgendaViewModel),
      issues: safelyBuildViewModel("issues", buildPolicyAgendaViewModel)
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
    if (model.state === "loading" && window.FR27UI) {
      return window.FR27UI.skeletonMarkup("list");
    }
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

    const latestAcceptedValue =
      renderStrongDateOrUnavailable(
        model.latestAcceptedAt,
        {
          timeZone: "Europe/Paris",
          day: "numeric",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          hourCycle: "h23",
          timeZoneName: "short"
        },
        () => formatNewsDateTime(
          model.latestAcceptedAt
        )
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
      <span class="hybrid-summary-meta" style="margin-top:8px">${translate(
        "signal_board.media.latest_accepted_item",
        "Latest accepted item: " +
          latestAcceptedValue,
        {
          dateOrUnavailable: latestAcceptedValue
        }
      )}</span>`,
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

  function renderSummaryGrid(models) {
    return `<div class="hybrid-summary-grid">
      ${renderRunoffSummary(models.runoff)}
      ${renderMediaSummary(models.media)}
      ${renderAgendaSummary(models.agenda)}
    </div>`;
  }

  function sourceLink(url, label, className = "", accessibleLabel = "") {
    const safe = safeSourceUrl(url);
    return safe
      ? `<a class="${className}" data-fr27-type="action-label" href="${escapeAttribute(safe)}" target="_blank" rel="noopener noreferrer"${accessibleLabel ? ` aria-label="${escapeAttribute(accessibleLabel)}"` : ""}>${escapeHtml(label)} <span aria-hidden="true">↗</span></a>`
      : `<span class="${className}" data-fr27-type="meta">Source unavailable</span>`;
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

  function workspaceTabIconMarkup(name) {
    const paths = {
      runoff: '<path d="M4 5h5v5H4zM15 5h5v5h-5zM9 7.5h6M12 7.5v9M8 19h8M9 16h6"/>',
      candidates: '<circle cx="12" cy="8" r="3.2"/><path d="M5.5 20c.5-4.5 2.7-6.8 6.5-6.8s6 2.3 6.5 6.8"/>',
      events: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M8 3v4M16 3v4M3.5 9.5h17M8 13h3M8 16.5h5"/>',
      agenda: '<path d="M7 6h12M7 12h12M7 18h12"/><circle cx="4" cy="6" r=".8"/><circle cx="4" cy="12" r=".8"/><circle cx="4" cy="18" r=".8"/>',
      issues: '<circle cx="7" cy="7" r="2"/><circle cx="17" cy="7" r="2"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/><path d="M9 7h6M7 9v6M17 9v6M9 17h6"/>',
    };

    const body = paths[name] || paths.runoff;
    return `<svg class="hybrid-tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  }

  function runoffCompactSourceLink(url, accessibleLabel) {
    const safe = safeSourceUrl(url);
    return safe
      ? `<a class="hybrid-runoff-source is-compact is-icon-only" data-fr27-type="action-label" href="${escapeAttribute(safe)}" target="_blank" rel="noopener noreferrer" aria-label="${escapeAttribute(accessibleLabel)}"><span aria-hidden="true">↗</span></a>`
      : '<span class="hybrid-runoff-source is-compact is-icon-only" data-fr27-type="meta">—</span>';
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
  function observationMarkup(observation, candidates, featuredObservation = null) {
    const scores = runoffScoresForCandidates(observation, candidates);
    const isFeatured = Boolean(
      featuredObservation &&
      (
        observation === featuredObservation ||
        (
          observation.event_id &&
          featuredObservation.event_id &&
          observation.event_id === featuredObservation.event_id
        )
      )
    );
    const scoreRole = isFeatured ? "focal-data" : "key-data";

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

    return `<article class="hybrid-observation hybrid-runoff-source-observation" tabindex="0"${isFeatured ? ' data-runoff-featured-observation="true"' : ""} data-fr27-tooltip="${escapeAttribute(tooltip)}" data-runoff-hover="RUNOFF_HOVER_METADATA">
      <div class="hybrid-runoff-candidate">
        <span class="hybrid-runoff-candidate-name" data-fr27-type="row-label">${escapeHtml(candidates[0])}</span>
        <span class="hybrid-runoff-candidate-result">${portraitMarkup(candidates[0])}<strong data-fr27-type="${scoreRole}">${percent(scores[0])}</strong></span>
      </div>

      <div class="hybrid-runoff-instrument">
        <div class="hybrid-runoff-observation-head">
          <strong data-fr27-type="item-title">${escapeHtml(observation.pollster)}</strong>
          <span data-fr27-type="meta">${escapeHtml(fieldworkLabel)}${sampleLabel ? ` · ${escapeHtml(sampleLabel)}` : ""}</span>
        </div>

        ${runoffBalanceRail(observation, candidates)}

        ${runoffCompactSourceLink(
          observation.source_url,
          `Open ${observation.pollster} source for ${candidates.join(" versus ")}`
        )}
      </div>

      <div class="hybrid-runoff-candidate is-right">
        <span class="hybrid-runoff-candidate-name" data-fr27-type="row-label">${escapeHtml(candidates[1])}</span>
        <span class="hybrid-runoff-candidate-result"><strong data-fr27-type="${scoreRole}">${percent(scores[1])}</strong>${portraitMarkup(candidates[1])}</span>
      </div>

      <div class="hybrid-runoff-margin-tile">
        <span data-fr27-type="field-label">MARGIN</span>
        <strong data-fr27-type="data">${number(observation.margin)}</strong>
        <small data-fr27-type="field-label">pts</small>
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
        <div><h2 data-fr27-type="panel-title">RUNOFF SIGNALS</h2><p data-fr27-type="body">Source-separated second-round evidence · no averages · no forecast</p></div>
      </div>
      <div class="hybrid-runoff-current-scope" aria-label="Current exact-window scope">
        <span class="hybrid-runoff-status is-${escapeAttribute(model.status)}" data-fr27-type="status-label">${escapeHtml(model.statusLabel).toUpperCase()}</span>
        <span class="hybrid-runoff-scope-message" data-fr27-type="body">${escapeHtml(explanation)}</span>
        <strong class="hybrid-runoff-date-pill" data-fr27-type="meta">${runoffIconMarkup("calendar", "hybrid-runoff-inline-icon")}<span>${escapeHtml(runoffTitleCaseDate(model.fieldworkLabel))}</span></strong>
      </div>
      <div class="hybrid-runoff-header-metrics" aria-label="Full archive counts">${counters.map(counter => `<span class="hybrid-runoff-header-metric"><strong data-fr27-type="key-data">${counter[0]}</strong><small data-fr27-type="field-label">${counter[1]}</small></span>`).join("")}</div>
    </header>`;
  }
  function renderRunoffClosest(model) {
    if (model.status === "agree" && model.selectedMatchup) {
      const matchup = model.selectedMatchup;
      const narrowest = Math.min(...matchup.observations.map(item => Number(item.margin)));
      return `<section class="hybrid-runoff-module hybrid-runoff-closest" aria-labelledby="hybrid-runoff-closest-title">
        <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">1</span><h3 id="hybrid-runoff-closest-title" data-fr27-type="module-title">CLOSEST TESTED RUNOFF</h3></div><span data-fr27-type="meta">Same closest matchup · different reported distance</span></div>
        <h4 data-fr27-type="item-title">${escapeHtml(matchup.candidates.join(" vs "))}</h4>
        <div class="hybrid-runoff-observations">${matchup.observations.map(item => observationMarkup(item, matchup.candidates, model.featuredObservation)).join("")}</div>
        <div class="hybrid-runoff-closest-callout">${runoffIconMarkup("target", "hybrid-runoff-callout-icon")}<strong data-fr27-type="data">NARROWEST OBSERVED MARGIN · ${number(narrowest)} PTS</strong></div>
      </section>`;
    }

    if (["split", "ambiguous"].includes(model.status)) {
      const explanation = model.status === "split"
        ? "Pollsters identify different uniquely closest matchups in the common tested set."
        : "At least one pollster has multiple matchups tied at its minimum reported margin.";
      return `<section class="hybrid-runoff-module hybrid-runoff-closest" aria-labelledby="hybrid-runoff-closest-title">
        <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">1</span><h3 id="hybrid-runoff-closest-title" data-fr27-type="module-title">CLOSEST TESTED RUNOFF</h3></div><span data-fr27-type="status-label">${escapeHtml(model.statusLabel)}</span></div>
        <p class="hybrid-runoff-local-state" data-fr27-type="body">${escapeHtml(explanation)}</p>
        <div class="hybrid-runoff-unresolved-grid">${model.pollsters.map(pollster => `<section class="hybrid-runoff-unresolved-source"><h4 data-fr27-type="item-title">${escapeHtml(pollster.pollster)}</h4>${pollster.closest_matchups.map(matchup => `<div class="hybrid-runoff-unresolved-row"><strong data-fr27-type="row-label">${escapeHtml(matchup.candidates.join(" vs "))}</strong><span data-fr27-type="key-data">${escapeHtml(runoffScorePair(matchup.result, matchup.candidates))} · ${number(matchup.result.margin)} pts</span>${sourceLink(matchup.result.source_url, "SOURCE", "hybrid-runoff-source is-compact")}</div>`).join("")}</section>`).join("")}</div>
      </section>`;
    }

    return `<section class="hybrid-runoff-module hybrid-runoff-closest" aria-labelledby="hybrid-runoff-closest-title">
      <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">1</span><h3 id="hybrid-runoff-closest-title" data-fr27-type="module-title">CLOSEST TESTED RUNOFF</h3></div></div>
      <div class="hybrid-runoff-local-state" data-fr27-type="status-label" role="status">No score comparison is shown. A qualifying window requires at least two pollsters, at least two tested matchups per pollster, and at least two exact common matchup keys.</div>
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
      <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">2</span><div><h3 id="hybrid-runoff-common-title" data-fr27-type="module-title">CURRENT COMMON MATCHUPS</h3></div></div></div>
      ${model.commonMatchups.length ? `<div class="hybrid-runoff-matrix" role="table" aria-label="Current common matchup source results">
        <div class="hybrid-runoff-matrix-head" role="row"><span role="columnheader" data-fr27-type="field-label">MATCHUP</span>${pollsters.map(name => `<span role="columnheader" data-fr27-type="field-label">${escapeHtml(name)}</span>`).join("")}<span role="columnheader" data-fr27-type="field-label">MARGINS</span></div>
        ${displayMatchups.map(matchup => {
          const selected = model.selectedMatchup?.key === matchup.matchup_key;
          const margins = pollsters.map(name => matchup.results.find(item => item.pollster === name)?.margin);
          return `<div class="hybrid-runoff-matrix-row${selected ? " is-selected" : ""}" role="row">
            <span class="hybrid-runoff-matrix-matchup" role="rowheader" data-fr27-type="row-label">${selected ? '<small>CLOSEST COMMON MATCHUP</small>' : ""}<strong>${escapeHtml(matchup.candidates[0] || "")}<br>vs ${escapeHtml(matchup.candidates[1] || "")}</strong></span>
            ${pollsters.map(name => {
              const result = matchup.results.find(item => item.pollster === name);
              if (!result) return `<span class="hybrid-runoff-matrix-result" role="cell" data-fr27-type="meta">—</span>`;
              const scores = runoffScoresForCandidates(result, matchup.candidates);
              return `<span class="hybrid-runoff-matrix-result" role="cell"><span class="hybrid-runoff-matrix-score is-left" data-fr27-type="data">${percent(scores[0])}</span>${runoffCompactRail(result, matchup.candidates)}<span class="hybrid-runoff-matrix-score is-right" data-fr27-type="data">${percent(scores[1])}</span></span>`;
            }).join("")}
            <span class="hybrid-runoff-matrix-margins" role="cell"><strong data-fr27-type="data">${margins.map(value => number(value)).join(" / ")}</strong><small data-fr27-type="field-label">pts</small></span>
          </div>`;
        }).join("")}
      </div>` : `<div class="hybrid-runoff-local-state" data-fr27-type="status-label" role="status">No common exact-window matchup matrix is available for this status.</div>`}
      <div class="hybrid-runoff-matrix-legend"><span><i class="is-left"></i>Candidate 1</span><span><i class="is-right"></i>Candidate 2</span><span>Exact source-reported scores · no averages</span></div>
    </section>`;
  }
  function renderRunoffFootprint(model) {
    if (model.archive.state !== "ready") {
      return `<section class="hybrid-runoff-module hybrid-runoff-footprint" aria-labelledby="hybrid-runoff-footprint-title"><div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">3</span><h3 id="hybrid-runoff-footprint-title" data-fr27-type="module-title">EVIDENCE FOOTPRINT</h3></div></div><div class="hybrid-runoff-local-state" data-fr27-type="status-label" role="status" aria-live="polite">${escapeHtml(model.archive.message)}</div></section>`;
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
      <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">3</span><h3 id="hybrid-runoff-footprint-title" data-fr27-type="module-title">EVIDENCE FOOTPRINT</h3></div></div>
      <dl class="hybrid-runoff-footprint-grid">${metrics.map(metric => `<div class="hybrid-runoff-metric">${runoffIconMarkup(metric[2], "hybrid-runoff-metric-icon")}<dd><strong data-fr27-type="key-data">${metric[0]}</strong></dd><dt data-fr27-type="field-label">${metric[1]}</dt></div>`).join("")}</dl>
      <div class="hybrid-runoff-window-range">
        <article><span data-fr27-type="field-label">EARLIEST EVIDENCE</span><strong data-fr27-type="scale-label">${escapeHtml(earliestYear)}</strong><b data-fr27-type="scale-label">${escapeHtml(runoffMonthYear(footprint.earliestWindow))}</b><small data-fr27-type="meta">${escapeHtml(runoffTitleCaseDate(exactRunoffWindowLabel(footprint.earliestWindow)))}</small></article>
        <article><span data-fr27-type="field-label">LATEST EVIDENCE</span><strong data-fr27-type="scale-label">${escapeHtml(runoffMonthYear(footprint.latestWindow))}</strong><small data-fr27-type="meta">${escapeHtml(runoffTitleCaseDate(exactRunoffWindowLabel(footprint.latestWindow)))}</small></article>
      </div>
      <p class="hybrid-runoff-module-note" data-fr27-type="meta">Source-linked evidence · no synthesis · no forecast</p>
    </section>`;
  }
  function renderRunoffHistory(model) {
    if (model.archive.state !== "ready") {
      return `<section class="hybrid-runoff-module hybrid-runoff-history" aria-labelledby="hybrid-runoff-history-title"><div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">4</span><h3 id="hybrid-runoff-history-title" data-fr27-type="module-title">SELECTED MATCHUP HISTORY</h3></div></div><div class="hybrid-runoff-local-state" data-fr27-type="status-label" role="status" aria-live="polite">${escapeHtml(model.archive.message)}</div></section>`;
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
            <h3 id="hybrid-runoff-history-title" data-fr27-type="module-title">SELECTED MATCHUP HISTORY</h3>
            <p data-fr27-type="meta">${escapeHtml(selected?.candidates.join(" vs ") || "Exact matchup")} · Discrete source observations only</p>
          </div>
        </div>

        <label data-fr27-type="field-label">
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

              <time data-fr27-type="scale-label" datetime="${escapeAttribute(event.fieldwork_end)}">${escapeHtml(runoffTitleCaseDate(exactRunoffWindowLabel(event)))}</time>

              <div class="hybrid-runoff-history-group">
                <article class="hybrid-runoff-history-entry" tabindex="0" data-fr27-tooltip="${escapeAttribute(`${runoffTitleCaseDate(exactRunoffWindowLabel(event))} · ${event.pollster} · ${percent(scores[0])}–${percent(scores[1])} · Margin ${number(event.margin)} pts · ${runoffSampleLabel(event.sample_size)}`)}" data-runoff-hover="RUNOFF_HOVER_METADATA">
                  <strong class="hybrid-runoff-history-pollster" data-fr27-type="row-label">${escapeHtml(event.pollster)}${runoffCompactSourceLink(
                      event.source_url,
                      `Open ${event.pollster} source for ${candidates.join(" versus ")}`
                    )}</strong>

                  <span class="hybrid-runoff-history-scores">
                    <b data-fr27-type="data">${percent(scores[0])}</b>
                    <i>–</i>
                    <b data-fr27-type="data">${percent(scores[1])}</b>
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
      return `<section class="hybrid-runoff-module hybrid-runoff-others" aria-labelledby="hybrid-runoff-others-title"><div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">5</span><h3 id="hybrid-runoff-others-title" data-fr27-type="module-title">OTHER TESTED MATCHUPS</h3></div></div><div class="hybrid-runoff-local-state" data-fr27-type="status-label" role="status" aria-live="polite">${escapeHtml(model.archive.message)}</div></section>`;
    }
    return `<section class="hybrid-runoff-module hybrid-runoff-others" aria-labelledby="hybrid-runoff-others-title">
      <div class="hybrid-runoff-module-head"><div><span class="hybrid-runoff-step" aria-hidden="true">5</span><h3 id="hybrid-runoff-others-title" data-fr27-type="module-title">OTHER TESTED MATCHUPS</h3></div><span data-fr27-type="meta">Evidence catalogue · latest reported source result shown</span></div>
      <div class="hybrid-runoff-other-grid">${model.archive.otherMatchups.map(matchup => {
        const event = matchup.latest;
        const scores = runoffScoresForCandidates(event, matchup.candidates);
        const sourceLabel = `Open ${event.pollster} source for ${matchup.candidates.join(" versus ")}`;
        return `<article class="hybrid-runoff-other-card" tabindex="0" data-fr27-tooltip="${escapeAttribute(`${event.pollster} · ${runoffTitleCaseDate(exactRunoffWindowLabel(event))} · Margin ${number(event.margin)} pts · ${runoffSampleLabel(event.sample_size)}`)}" data-runoff-hover="RUNOFF_HOVER_METADATA"><h4 data-fr27-type="row-label"><span>${escapeHtml(matchup.candidates[0])}</span><small>vs ${escapeHtml(matchup.candidates[1])}</small></h4><span class="hybrid-runoff-other-meta" data-fr27-type="meta">${escapeHtml(event.pollster)} · ${escapeHtml(runoffTitleCaseDate(exactRunoffWindowLabel(event)))}</span><div class="hybrid-runoff-other-score"><strong data-fr27-type="data">${percent(scores[0])}</strong>${runoffCompactRail(event, matchup.candidates)}<strong data-fr27-type="data">${percent(scores[1])}</strong></div><div class="hybrid-runoff-other-foot"><span data-fr27-type="data">MARGIN · ${number(event.margin)} PTS</span><span data-fr27-type="field-label">${escapeHtml(runoffSampleLabel(event.sample_size))}</span>${runoffCompactSourceLink(event.source_url, sourceLabel)}</div></article>`;
      }).join("")}</div>
    </section>`;
  }
  function renderRunoffPanel(model) {
    if (model.state !== "ready" && model.status !== "insufficient") {
      if (model.state === "loading" && window.FR27UI) {
        return window.FR27UI.skeletonElement(
          "runoff",
          "Loading runoff evidence"
        ).outerHTML;
      }
      return `<div class="hybrid-runoff-local-state" data-fr27-type="status-label" role="status" aria-live="polite">${escapeHtml(model.message || "Runoff evidence is unavailable.")}</div>`;
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
              data-fr27-type="meta"
            >${escapeHtml(
              formatNewsDateTime(item.published_at)
            )}</time>

            <span
              class="hybrid-media-terminal-publisher"
              data-fr27-type="meta"
            >${escapeHtml(item.publisher)}</span>

            <span class="hybrid-media-terminal-copy">
              <span
                class="hybrid-media-terminal-headline"
                data-fr27-type="item-title"
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
                `${item.name}, ${item.tierLabel}: ${latestShareText} percent mention rate among active-field-linked race records in the latest seven days, ${previousShareText} percent in the previous seven days, ${deltaText}; ${item.latestCount} latest records and ${item.previousCount} previous records`
              )}"
            >
              <span class="hybrid-candidate-share-name" data-fr27-type="row-label">
                ${escapeHtml(item.name)}
              </span>
                <small class="hybrid-status-chip" data-fr27-type="status-label">${escapeHtml(item.tierLabel)}</small>

              <strong data-fr27-type="data">${latestShareText}%</strong>

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

              <b class="${directionClass}" data-fr27-type="${deltaAvailable ? "data" : "meta"}">
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
                    data-fr27-type="scale-label"
                    aria-hidden="true"
                  >${String(index + 1).padStart(2, "0")}</span>

                  <span class="hybrid-topic-matrix-label" data-fr27-type="row-label">
                    ${escapeHtml(topic.label)}
                  </span>

                  <strong class="hybrid-topic-matrix-days" data-fr27-type="${sourceDaysAvailable ? "data" : "meta"}">
                    ${sourceDaysText}
                  </strong>

                  <strong class="hybrid-topic-matrix-pubs" data-fr27-type="${publishersAvailable ? "data" : "meta"}">
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
            <h3 class="hybrid-section-title" data-fr27-type="module-title">
              Recent election coverage
            </h3>

            <span class="hybrid-media-terminal-status" data-fr27-type="meta">
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
            <h3 class="hybrid-section-title" data-fr27-type="module-title">
              Active-field mention rate
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
                  <strong data-fr27-type="field-label">CURRENT</strong>
                  <small data-fr27-type="scale-label">${escapeHtml(currentPeriodLabel)}</small>
                </span>
              </span>

              <span class="hybrid-coverage-period">
                <i
                  class="hybrid-coverage-period-swatch is-prior"
                  aria-hidden="true"
                ></i>
                <span>
                  <strong data-fr27-type="field-label">PRIOR</strong>
                  <small data-fr27-type="scale-label">${escapeHtml(priorPeriodLabel)}</small>
                </span>
              </span>
            </div>

            <div class="hybrid-candidate-share-list">
              ${candidateRows}
            </div>
          </section>

          <section class="hybrid-media-terminal-module">
            <h3 class="hybrid-section-title" data-fr27-type="module-title">
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
                <strong data-fr27-type="field-label">DAYS</strong>
                <strong data-fr27-type="field-label">PUBS</strong>
              </div>

              ${topicRows}
            </div>
          </section>
        </aside>
      </div>`;
  }

  function agendaSignedPp(value) {
    const numeric = number(value);
    return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}pp`;
  }

  function agendaPercent(value, digits = 1) {
    return `${(number(value) * 100).toFixed(digits)}%`;
  }

  function agendaCompactDate(value) {
    const match = String(value || "").match(
      /^(\d{4})-(\d{2})-(\d{2})$/
    );

    if (!match) return value || "";

    const months = [
      "JAN", "FEB", "MAR", "APR",
      "MAY", "JUN", "JUL", "AUG",
      "SEP", "OCT", "NOV", "DEC"
    ];

    return `${Number(match[3])} ${months[Number(match[2]) - 1]}`;
  }

  function agendaPeriodLabel(startValue, endValue) {
    const start = String(startValue || "").match(
      /^(\d{4})-(\d{2})-(\d{2})$/
    );

    const end = String(endValue || "").match(
      /^(\d{4})-(\d{2})-(\d{2})$/
    );

    if (!start || !end) {
      return `${startValue || ""}–${endValue || ""}`;
    }

    const months = [
      "JAN", "FEB", "MAR", "APR",
      "MAY", "JUN", "JUL", "AUG",
      "SEP", "OCT", "NOV", "DEC"
    ];

    const startDay = Number(start[3]);
    const endDay = Number(end[3]);
    const startMonth = months[Number(start[2]) - 1];
    const endMonth = months[Number(end[2]) - 1];

    if (start[2] === end[2]) {
      return `${startDay}–${endDay} ${endMonth}`;
    }

    return `${startDay} ${startMonth}–${endDay} ${endMonth}`;
  }

  function agendaSignalLabel(value) {
    const cleaned = String(value || "")
      .replaceAll("_", " ")
      .trim();

    if (!cleaned) return "";

    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  }

  function agendaTopicIcon(topicId) {
    const icons = {
      selection_strategy: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <path d="M3 15V9M7 15V5M11 15V8M15 15V3"/>
          <path d="M2 15.5h14"/>
        </svg>`,
      candidacies_endorsements: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <circle cx="7" cy="5" r="2.2"/>
          <circle cx="12.5" cy="6.5" r="1.7"/>
          <path d="M2.8 14c.3-3 1.8-4.5 4.2-4.5S11 11 11.3 14"/>
          <path d="M10.7 10.5c2.8-.1 4.2 1.1 4.5 3.5"/>
        </svg>`,
      legal_eligibility: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <path d="M9 2v13M4 5h10"/>
          <path d="M4 5 2 10h4L4 5ZM14 5l-2 5h4l-2-5Z"/>
          <path d="M5 15h8"/>
        </svg>`,
      polls_race: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <rect x="3" y="3" width="12" height="12" rx="1"/>
          <path d="M6 12V9M9 12V6M12 12V8"/>
        </svg>`,
      rules_calendar: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <path d="M9 2.2 15 5v4.2c0 3.1-2.2 5.2-6 6.6-3.8-1.4-6-3.5-6-6.6V5l6-2.8Z"/>
          <path d="m6.2 9 1.8 1.8 3.8-4"/>
        </svg>`
    };

    return icons[topicId] || `
      <svg viewBox="0 0 18 18" aria-hidden="true">
        <circle cx="9" cy="9" r="5.5"/>
      </svg>`;
  }

  function renderLegacyAgendaPanel(model) {
    const selected = model.selectedTopic;

    const definitionAvailable =
      typeof selected.definition === "string" &&
      Boolean(selected.definition.trim());

    const definition = definitionAvailable
      ? selected.definition.trim()
      : "Topic definition unavailable in the current repository data.";

    return `<div class="hybrid-agenda-layout">
      <section class="hybrid-agenda-ranking">
        <h3 class="hybrid-section-title" data-fr27-type="module-title">Eligible-topic ranking</h3>
        <p class="hybrid-section-sub" data-fr27-type="meta">Accepted election-news topics · ${model.windowDays}-day source window. Primary bar value: source-day recurrence.</p>

        ${model.topics.map((topic, index) => `
          <button
            class="hybrid-agenda-topic"
            type="button"
            data-hybrid-agenda-topic="${escapeAttribute(topic.id)}"
            aria-pressed="${String(topic.id === selected.id)}"
          >
            <span class="hybrid-agenda-topic-head">
              <span data-fr27-type="item-title">${index + 1}. ${escapeHtml(topic.label)}</span>
              <strong data-fr27-type="data">${topic.source_day_count} source-days</strong>
            </span>

            <span class="hybrid-agenda-topic-meta" data-fr27-type="meta">
              ${countLabel(topic.item_count, "item")} ·
              ${countLabel(topic.publisher_count, "publisher")} ·
              ${countLabel(topic.active_day_count, "active day")}
            </span>

            <span class="hybrid-track" aria-hidden="true">
              <span
                class="hybrid-fill"
                style="--hybrid-width:${(
                  number(topic.source_day_count) /
                  model.maxSourceDays *
                  100
                ).toFixed(1)}%"
              ></span>
            </span>
          </button>
        `).join("")}
      </section>

      <section class="hybrid-agenda-detail" aria-live="polite">
        <div class="hybrid-section-title" data-fr27-type="kicker">Selected recurring topic</div>
        <h3 data-fr27-type="item-title">${escapeHtml(selected.label)}</h3>

        <p class="hybrid-agenda-definition${definitionAvailable ? "" : " is-unavailable"}" data-fr27-type="${definitionAvailable ? "body" : "meta"}">
          ${escapeHtml(definition)}
        </p>

        <div class="hybrid-metrics">
          <span class="hybrid-metric" data-fr27-type="data">${selected.source_day_count} source-days</span>
          <span class="hybrid-metric" data-fr27-type="data">${countLabel(selected.item_count, "accepted item")}</span>
          <span class="hybrid-metric" data-fr27-type="data">${countLabel(selected.publisher_count, "publisher")}</span>
          <span class="hybrid-metric" data-fr27-type="data">${countLabel(selected.active_day_count, "active day")}</span>
        </div>

        <div class="hybrid-supporting-list">
          ${selected.supporting_items.slice(0, 5).map(item => `
            <a
              class="hybrid-supporting-link" data-fr27-type="action-label"
              href="${escapeAttribute(safeSourceUrl(item.url))}"
              target="_blank"
              rel="noopener noreferrer"
            >
              <span class="hybrid-supporting-meta" data-fr27-type="meta">
                ${escapeHtml(item.publisher)} · ${formatDay(item.published_at)}
              </span>
              <span lang="fr" data-fr27-type="item-title">
                ${escapeHtml(item.headline)}
                <span aria-hidden="true">↗</span>
              </span>
            </a>
          `).join("") || '<div class="hybrid-state is-compact">No supporting source-linked items are available for this topic.</div>'}
        </div>
      </section>
    </div>

    <p class="hybrid-disclosure" data-fr27-type="body">
      Recurring campaign topics classify accepted presidential-election coverage from monitored publishers. Bars use source-day count, not raw article volume. This is agenda activity, not voter or public priorities.
    </p>`;
  }

  function agendaWindowRole(day, evolution) {
    const value = String(day?.date || "");

    if (
      evolution?.period_end_partial &&
      value === evolution.period_end
    ) {
      return "partial";
    }

    if (
      value >= String(evolution?.latest_start || "") &&
      value <= String(evolution?.latest_end || "")
    ) {
      return "latest";
    }

    if (
      value >= String(evolution?.previous_start || "") &&
      value <= String(evolution?.previous_end || "")
    ) {
      return "previous";
    }

    return "older";
  }

  function renderAgendaV6Monitor(model) {
    const diagnostics = model.diagnostics;
    const selected = model.selectedEvolutionTopic;
    const maximumSourceDays = Math.max(
      1,
      ...model.evolutionTopics.map(topic => number(topic.source_day_count))
    );

    const diagnosticMarkup = diagnostics
      ? `<div class="hybrid-agenda-v6-diagnostics" aria-label="Agenda diagnostics">
          <article class="is-active">
            <span data-fr27-type="field-label">ACTIVE TOPICS</span>
            <strong data-fr27-type="key-data">${diagnostics.activeTopics}</strong>
          </article>
          <article class="is-concentration">
            <span data-fr27-type="field-label">TOP-3 SHARE</span>
            <strong data-fr27-type="key-data">${number(diagnostics.top3Share).toFixed(1)}%</strong>
          </article>
          <article class="is-rising">
            <span data-fr27-type="field-label">RISING TOPICS</span>
            <strong data-fr27-type="key-data">${diagnostics.risingTopics}</strong>
          </article>
          <article class="is-turnover">
            <span data-fr27-type="field-label">TOP-3 TURNOVER</span>
            <strong data-fr27-type="key-data">${diagnostics.top3Turnover}/${diagnostics.top3TurnoverDenominator}</strong>
          </article>
        </div>`
      : "";

    const rows = model.evolutionTopics.map(topic => {
      const isSelected = topic.id === selected?.id;
      const movement = String(topic.movement || "STABLE").toLowerCase();
      const volumeWidth = Math.max(
        4,
        number(topic.source_day_count) / maximumSourceDays * 100
      );
      const movementGlyph = movement === "rising"
        ? "▲"
        : movement === "fading"
          ? "▼"
          : "•";

      return `<button
        class="hybrid-agenda-v6-topic-card"
        type="button"
        data-hybrid-agenda-topic="${escapeAttribute(topic.id)}"
        data-movement="${escapeAttribute(movement)}"
        aria-pressed="${String(isSelected)}"
      >
        <span class="hybrid-agenda-v6-topic-icon" aria-hidden="true">
          ${agendaTopicIcon(topic.id)}
        </span>

        <span class="hybrid-agenda-v6-topic-copy">
          <span class="hybrid-agenda-v6-topic-name" data-fr27-type="item-title">${escapeHtml(topic.label)}</span>
          <span class="hybrid-agenda-v6-topic-tags">
            <span
              class="hybrid-agenda-v6-badge"
              data-movement="${escapeAttribute(movement)}"
              data-fr27-type="status-label"
            >${escapeHtml(topic.movement)}</span>
            <span class="hybrid-agenda-v6-badge is-structure" data-fr27-type="status-label">${escapeHtml(topic.structure)}</span>
          </span>
        </span>

        <span class="hybrid-agenda-v6-topic-total">
          <strong data-fr27-type="data">${topic.source_day_count}</strong>
          <span data-fr27-type="field-label">SOURCE-DAYS</span>
          <i class="hybrid-agenda-v6-topic-volume" aria-hidden="true">
            <b style="--agenda-monitor-volume:${volumeWidth.toFixed(1)}%"></b>
          </i>
        </span>

        <span class="hybrid-agenda-v6-topic-shift">
          <span>
            <small data-fr27-type="field-label">PRIOR</small>
            <strong data-fr27-type="data">${topic.previousSourceDays}</strong>
          </span>
          <span>
            <small data-fr27-type="field-label">LATEST</small>
            <strong data-fr27-type="data">${topic.latestSourceDays}</strong>
          </span>
          <em data-movement="${escapeAttribute(movement)}" data-fr27-type="data">
            ${movementGlyph} ${escapeHtml(agendaSignedPp(topic.agendaShareChangePp))}
          </em>
        </span>
      </button>`;
    }).join("");

    return `<section class="hybrid-agenda-v6-panel hybrid-agenda-v6-monitor">
      <header class="hybrid-agenda-v6-panel-head">
        <h3 class="hybrid-agenda-v6-panel-title" data-fr27-type="panel-title">AGENDA MONITOR</h3>
        <span class="hybrid-agenda-v6-panel-meta" data-fr27-type="meta">
          ${diagnostics ? `${diagnostics.activeTopics} ACTIVE · 30D` : "30D"}
        </span>
      </header>

      <div class="hybrid-agenda-v6-panel-body hybrid-agenda-v6-monitor-body">
        ${diagnosticMarkup}
        <div class="hybrid-agenda-v6-topic-list">
          ${rows}
        </div>
      </div>
    </section>`;
  }

  function agendaDailyCellV6(day, index, maxSourceDays, evolution) {
    const value = number(day?.source_day_count);
    const ratio = maxSourceDays ? Math.min(1, value / maxSourceDays) : 0;
    const alpha = value === 0 ? 0 : 0.28 + ratio * 0.72;
    const role = agendaWindowRole(day, evolution);

    return `<span
      class="hybrid-agenda-v6-day${index > 0 && index % 5 === 0 ? " is-period-start" : ""}${value === 0 ? " is-zero" : ""}"
      data-agenda-day-cell="true"
      data-agenda-window="${escapeAttribute(role)}"
      style="--agenda-day-alpha:${alpha.toFixed(3)}"
    ></span>`;
  }

  function renderAgendaV6Matrix(model) {
    const selected = model.selectedEvolutionTopic;
    const compactLabels = {
      "Primaries & party strategy": "Primaries & strategy",
      "Candidacies & endorsements": "Candidacies & endors.",
      "Legal cases & eligibility": "Legal & eligibility",
      "Polling & race narratives": "Polling & race",
      "Rules, calendar & campaign mechanics": "Rules & mechanics"
    };

    const periodHeaders = model.evolutionBins.map(bin => `
      <span class="hybrid-agenda-v6-period" data-fr27-type="scale-label">
        ${escapeHtml(agendaPeriodLabel(bin.start, bin.end))}
      </span>
    `).join("");

    const rows = model.evolutionTopics.map(topic => {
      const daily = Array.isArray(topic.daily_activity)
        ? topic.daily_activity
        : [];
      const shortLabel = compactLabels[topic.label] || topic.label;

      return `<button
        class="hybrid-agenda-v6-matrix-row"
        type="button"
        data-hybrid-agenda-topic="${escapeAttribute(topic.id)}"
        aria-pressed="${String(topic.id === selected?.id)}"
        data-fr27-tooltip="${escapeAttribute(topic.label)}"
      >
        <span class="hybrid-agenda-v6-matrix-label" data-fr27-type="row-label">${escapeHtml(shortLabel)}</span>

        ${daily.map((day, index) =>
          agendaDailyCellV6(
            day,
            index,
            model.heatmapMaxSourceDays,
            model.evolution
          )
        ).join("")}

        <strong class="hybrid-agenda-v6-matrix-total" data-fr27-type="data">${topic.source_day_count}</strong>
      </button>`;
    }).join("");

    return `<section class="hybrid-agenda-v6-module hybrid-agenda-v6-matrix-module">
      <div class="hybrid-agenda-v6-module-head">
        <strong data-fr27-type="module-title">30-DAY EVOLUTION</strong>
        <span data-fr27-type="scale-label">
          ${escapeHtml(agendaCompactDate(model.evolution.period_start))}
          →
          ${escapeHtml(agendaCompactDate(model.evolution.period_end))}
        </span>
      </div>

      <div class="hybrid-agenda-v6-matrix-wrap">
        <div
          class="hybrid-agenda-v6-matrix"
          role="group"
          aria-label="Thirty-day Agenda evolution matrix"
        >
          <div class="hybrid-agenda-v6-matrix-head" aria-hidden="true">
            <span data-fr27-type="field-label">TOPIC</span>
            ${periodHeaders}
            <span data-fr27-type="scale-label">30D</span>
          </div>

          ${rows}
        </div>

        <div class="hybrid-agenda-v6-matrix-legend" aria-label="Agenda evolution color key">
          <span><i data-window="older"></i>OLDER</span>
          <span><i data-window="previous"></i>PRIOR 7D</span>
          <span><i data-window="latest"></i>LATEST 7D</span>
          <span><i data-window="partial"></i>PARTIAL DAY</span>
        </div>
      </div>
    </section>`;
  }

  function renderAgendaV6WeekShift(model) {
    const compactLabels = {
      "Primaries & party strategy": "Primaries & strategy",
      "Candidacies & endorsements": "Candidacies & endors.",
      "Legal cases & eligibility": "Legal & eligibility",
      "Polling & race narratives": "Polling & race",
      "Rules, calendar & campaign mechanics": "Rules & mechanics"
    };

    const maximum = Math.max(
      1,
      ...model.evolutionTopics.flatMap(topic => [
        number(topic.latestSourceDays),
        number(topic.previousSourceDays)
      ])
    );

    const rows = model.evolutionTopics.map(topic => {
      const latest = number(topic.latestSourceDays);
      const previous = number(topic.previousSourceDays);
      const movement = String(topic.movement || "STABLE").toLowerCase();
      const glyph = movement === "rising"
        ? "▲"
        : movement === "fading"
          ? "▼"
          : "•";
      const shortLabel = compactLabels[topic.label] || topic.label;

      return `<div
        class="hybrid-agenda-v6-shift-row"
        data-movement="${escapeAttribute(movement)}"
      >
        <span class="hybrid-agenda-v6-shift-label" data-fr27-type="row-label">${escapeHtml(shortLabel)}</span>

        <span
          class="hybrid-agenda-v6-pair-bars"
          aria-label="Prior ${previous} source-days; latest ${latest} source-days"
        >
          <span class="hybrid-agenda-v6-pair-track is-prior" aria-hidden="true">
            <i style="--agenda-width:${(previous / maximum * 100).toFixed(1)}%"></i>
          </span>
          <span class="hybrid-agenda-v6-pair-track is-latest" aria-hidden="true">
            <i style="--agenda-width:${(latest / maximum * 100).toFixed(1)}%"></i>
          </span>
        </span>

        <span
          class="hybrid-agenda-v6-shift-count"
          data-fr27-type="data"
        >${previous} → ${latest}</span>

        <strong
          class="hybrid-agenda-v6-shift-delta"
          data-movement="${escapeAttribute(movement)}"
          data-fr27-type="data"
        >${glyph} ${escapeHtml(agendaSignedPp(topic.agendaShareChangePp))}</strong>
      </div>`;
    }).join("");

    return `<section class="hybrid-agenda-v6-module hybrid-agenda-v6-shift-module">
      <div class="hybrid-agenda-v6-module-head">
        <strong data-fr27-type="module-title">WEEK SHIFT</strong>

        <span class="hybrid-agenda-v6-shift-key" data-fr27-type="scale-label">
          <span>
            <i class="is-prior" aria-hidden="true"></i>
            PRIOR ${escapeHtml(
              agendaPeriodLabel(
                model.evolution.previous_start,
                model.evolution.previous_end
              )
            )}
          </span>
          <span>
            <i class="is-latest" aria-hidden="true"></i>
            LATEST ${escapeHtml(
              agendaPeriodLabel(
                model.evolution.latest_start,
                model.evolution.latest_end
              )
            )}
          </span>
        </span>
      </div>

      <div class="hybrid-agenda-v6-shift-list">
        ${rows}
      </div>
    </section>`;
  }

  function renderAgendaV6Analysis(model) {
    return `<section class="hybrid-agenda-v6-panel hybrid-agenda-v6-evolution-panel">
      <header class="hybrid-agenda-v6-panel-head">
        <h3 data-fr27-type="panel-title">AGENDA EVOLUTION</h3>
        <span class="hybrid-agenda-v6-head-tools">
          <span class="hybrid-agenda-v6-panel-head-meta" data-fr27-type="meta">COMPLETE-WEEK COMPARISON</span>
          <button class="hybrid-agenda-v6-info fr27-info-glyph" type="button" aria-label="Agenda methodology" data-fr27-tooltip="Source-day = unique publisher × UTC date · exact 30D projection includes the current partial UTC day · movement compares latest 7 complete days with prior 7 · this measures monitored media agenda activity, not voter or public priorities.">
            <span aria-hidden="true">i</span>
          </button>
        </span>
      </header>

      <div class="hybrid-agenda-v6-panel-body hybrid-agenda-v6-evolution-body">
        ${renderAgendaV6Matrix(model)}
        ${renderAgendaV6WeekShift(model)}
      </div>
    </section>`;
  }

  function renderAgendaV6Activity(topic, evolution) {
    const daily = Array.isArray(topic.daily_activity)
      ? topic.daily_activity
      : [];

    const maxValue = Math.max(
      1,
      ...daily.map(day => number(day.source_day_count))
    );

    const activeDays30 = daily.filter(
      day => number(day.source_day_count) > 0
    ).length;

    const latestSeries = daily
      .filter(day => agendaWindowRole(day, evolution) === "latest")
      .map(day => number(day.source_day_count));

    const priorSeries = daily
      .filter(day => agendaWindowRole(day, evolution) === "previous")
      .map(day => number(day.source_day_count));

    const comparisonMax = Math.max(
      1,
      ...latestSeries,
      ...priorSeries
    );

    const renderSparkline = (values, tone, label) => {
      const width = 118;
      const height = 22;
      const left = 2;
      const right = 116;
      const top = 3;
      const bottom = 19;
      const step = values.length > 1
        ? (right - left) / (values.length - 1)
        : 0;

      const points = values.map((value, index) => {
        const x = left + (index * step);
        const y = bottom - (
          number(value) / comparisonMax * (bottom - top)
        );
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");

      const dots = values.map((value, index) => {
        const x = left + (index * step);
        const y = bottom - (
          number(value) / comparisonMax * (bottom - top)
        );

        return `<circle
          cx="${x.toFixed(1)}"
          cy="${y.toFixed(1)}"
          r="${number(value) > 0 ? "1.65" : "1.1"}"
        ></circle>`;
      }).join("");

      return `<svg
        class="hybrid-agenda-v6-week-sparkline"
        data-tone="${escapeAttribute(tone)}"
        viewBox="0 0 ${width} ${height}"
        preserveAspectRatio="none"
        role="img"
        aria-label="${escapeAttribute(label)}"
      >
        <line
          class="hybrid-agenda-v6-spark-baseline"
          x1="${left}"
          y1="${bottom}"
          x2="${right}"
          y2="${bottom}"
        ></line>
        <polyline
          class="hybrid-agenda-v6-spark-line"
          points="${escapeAttribute(points)}"
        ></polyline>
        <g class="hybrid-agenda-v6-spark-points">${dots}</g>
      </svg>`;
    };

    return `<section class="hybrid-agenda-v6-module hybrid-agenda-v6-profile-module">
      <div class="hybrid-agenda-v6-module-head">
        <strong data-fr27-type="module-title">ACTIVITY PROFILE · 30D</strong>
        <span data-fr27-type="scale-label">
          ${escapeHtml(agendaCompactDate(daily[0]?.date))}
          →
          ${escapeHtml(agendaCompactDate(daily[daily.length - 1]?.date))}
        </span>
      </div>

      <div class="hybrid-agenda-v6-profile-body">
        <div class="hybrid-agenda-v6-profile-top">
          <div
            class="hybrid-agenda-v6-bars"
            aria-label="Thirty-day selected-topic source-day activity"
          >
            ${daily.map(day => {
              const value = number(day.source_day_count);
              const role = agendaWindowRole(day, evolution);
              const height = value
                ? Math.max(10, value / maxValue * 100)
                : 2;

              return `<span
                class="${value === 0 ? "is-zero" : ""}"
                data-agenda-activity-day="true"
                data-agenda-window="${escapeAttribute(role)}"
                style="--agenda-bar-height:${height.toFixed(1)}%"
              ></span>`;
            }).join("")}
          </div>

          <div
            class="hybrid-agenda-v6-week-compare"
            aria-label="Prior and latest complete-week daily activity shapes"
          >
            <div class="hybrid-agenda-v6-week-line is-latest">
              <span data-fr27-type="scale-label">LATEST 7D</span>
              ${renderSparkline(
                latestSeries,
                "latest",
                `Latest 7D daily source-days: ${latestSeries.join(", ")}`
              )}
              <strong data-fr27-type="data">${topic.latestSourceDays}</strong>
            </div>

            <div class="hybrid-agenda-v6-week-line is-prior">
              <span data-fr27-type="scale-label">PRIOR 7D</span>
              ${renderSparkline(
                priorSeries,
                "prior",
                `Prior 7D daily source-days: ${priorSeries.join(", ")}`
              )}
              <strong data-fr27-type="data">${topic.previousSourceDays}</strong>
            </div>
          </div>
        </div>

        <div
          class="hybrid-agenda-v6-profile-facts"
          aria-label="Selected topic persistence and peak facts"
        >
          <div>
            <span data-fr27-type="field-label">ACTIVE · 14D</span>
            <strong data-fr27-type="key-data">${topic.activeDays14}/14</strong>
          </div>

          <div>
            <span data-fr27-type="field-label">ACTIVE · 30D</span>
            <strong data-fr27-type="key-data">${activeDays30}/30</strong>
          </div>

          <div>
            <span data-fr27-type="field-label">PEAK SHARE</span>
            <strong data-fr27-type="key-data">${escapeHtml(agendaPercent(topic.peakDayShare))}</strong>
          </div>

          <div>
            <span data-fr27-type="field-label">PEAK DAY</span>
            <strong data-fr27-type="key-data">${escapeHtml(agendaCompactDate(topic.peakDayDate))} · ${topic.peakDaySourceDays} SD</strong>
          </div>
        </div>
      </div>
    </section>`;
  }

  function renderAgendaV6Signals(topic) {
    const signals = Array.isArray(topic.associatedSignals)
      ? topic.associatedSignals.slice(0, 8)
      : [];

    if (!signals.length) {
      return `<div class="hybrid-agenda-v6-scroll" data-agenda-scroll-region="signals">
        <div class="hybrid-agenda-v6-empty">No associated classification signals are published.</div>
      </div>`;
    }

    const maximum = Math.max(1, ...signals.map(signal => number(signal.item_count)));

    return `<div class="hybrid-agenda-v6-scroll" data-agenda-scroll-region="signals">
      <div class="hybrid-agenda-v6-signal-list">
        ${signals.map(signal => {
          const count = number(signal.item_count);
          return `<div class="hybrid-agenda-v6-signal-item">
            <div class="hybrid-agenda-v6-signal-head">
              <span data-fr27-type="row-label">${escapeHtml(agendaSignalLabel(signal.term))}</span>
              <strong data-fr27-type="data">${count}</strong>
            </div>
            <span class="hybrid-agenda-v6-signal-track" aria-hidden="true">
              <i style="--agenda-signal-width:${(count / maximum * 100).toFixed(1)}%"></i>
            </span>
          </div>`;
        }).join("")}
      </div>
    </div>`;
  }


  const agendaSourceIconState = {
    status: "idle",
    records: new Map()
  };
  let agendaSourceIconRequest = null;

  function agendaNormalizePublisherIconKey(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[’']/g, " ")
      .replace(/[^a-zA-Z0-9]+/g, " ")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
  }

  function agendaPublisherIconKey(value) {
    const normalized = agendaNormalizePublisherIconKey(value);
    const aliases = new Map([
      ["franceinfo", "franceinfo politique"],
      ["lcp actualites", "lcp"],
      ["france 24 france", "france 24 francais"]
    ]);
    return aliases.get(normalized) || normalized;
  }

  function ensureAgendaSourceIcons(
    fetchImplementation =
      typeof window.fetch === "function"
        ? window.fetch.bind(window)
        : null
  ) {
    if (
      agendaSourceIconState.status !== "idle" ||
      agendaSourceIconRequest ||
      !fetchImplementation
    ) {
      return agendaSourceIconRequest;
    }

    agendaSourceIconState.status = "loading";

    agendaSourceIconRequest = fetchImplementation("source_icons.json")
      .then(response => {
        if (!response.ok) {
          throw new Error(
            `source_icons.json returned HTTP ${response.status}`
          );
        }
        return response.json();
      })
      .then(payload => {
        const sources = Array.isArray(payload?.sources)
          ? payload.sources
          : [];

        agendaSourceIconState.records.clear();

        sources.forEach(record => {
          if (
            !record ||
            record.status !== "ok" ||
            typeof record.publisher !== "string" ||
            typeof record.path !== "string" ||
            !record.path
          ) {
            return;
          }

          agendaSourceIconState.records.set(
            agendaPublisherIconKey(record.publisher),
            record.path
          );
        });

        agendaSourceIconState.status = "ready";

        if (typeof mount.querySelectorAll === "function") {
          renderAll();
        }

        return agendaSourceIconState;
      })
      .catch(error => {
        agendaSourceIconState.status = "unavailable";
        agendaSourceIconState.records.clear();
        console.warn("Agenda source icons unavailable.", error);
        return agendaSourceIconState;
      });

    return agendaSourceIconRequest;
  }

  function agendaPublisherIconPath(publisher) {
    ensureAgendaSourceIcons();

    return agendaSourceIconState.records.get(
      agendaPublisherIconKey(publisher)
    ) || "";
  }


  function renderAgendaV6Evidence(topic) {
    const allEvidence = Array.isArray(topic.supporting_items)
      ? topic.supporting_items
      : [];
    const evidence = allEvidence.slice(0, 8);

    if (!evidence.length) {
      return `<div
        class="hybrid-agenda-v6-scroll"
        data-agenda-scroll-region="evidence"
      >
        <div class="hybrid-agenda-v6-empty">
          No source-linked evidence is currently published.
        </div>
      </div>`;
    }

    return `<div
      class="hybrid-agenda-v6-scroll"
      data-agenda-scroll-region="evidence"
    >
      <div class="hybrid-agenda-v6-evidence-list">
        ${evidence.map(item => {
          const iconPath = agendaPublisherIconPath(item.publisher);
          const iconMarkup = iconPath
            ? `<span
                class="hybrid-agenda-v6-publisher-icon"
                aria-hidden="true"
              >
                <img
                  src="${escapeAttribute(iconPath)}"
                  alt=""
                  loading="lazy"
                  decoding="async"
                  onerror="this.parentElement.remove()"
                >
              </span>`
            : "";

          return `<a
            class="hybrid-agenda-v6-evidence-row ${iconPath ? "has-publisher-icon" : "has-no-publisher-icon"}" data-fr27-type="action-label"
            href="${escapeAttribute(safeSourceUrl(item.url))}"
            target="_blank"
            rel="noopener noreferrer"
          >
            <span class="hybrid-agenda-v6-evidence-copy">
              <strong lang="fr" data-fr27-type="item-title">${escapeHtml(item.headline)}</strong>
              <small data-fr27-type="meta">${escapeHtml(item.publisher)} · ${formatDay(item.published_at)}</small>
            </span>

            <i class="hybrid-agenda-v6-evidence-arrow" aria-hidden="true">↗</i>
            ${iconMarkup}
          </a>`;
        }).join("")}
      </div>
    </div>`;
  }

  function renderAgendaV6Dossier(model) {
    const topic = model.selectedEvolutionTopic;
    if (!topic) return "";

    const signals = Array.isArray(topic.associatedSignals)
      ? topic.associatedSignals
      : [];
    const signalCount = signals.length;
    const signalHits = signals.reduce(
      (total, signal) => total + number(signal.item_count),
      0
    );

    const evidenceCount = Array.isArray(topic.supporting_items)
      ? topic.supporting_items.length
      : 0;

    const movement = String(topic.movement || "STABLE").toLowerCase();

    return `<section class="hybrid-agenda-v6-panel hybrid-agenda-v6-dossier">
      <header class="hybrid-agenda-v6-panel-head">
        <h3 class="hybrid-agenda-v6-panel-title" data-fr27-type="panel-title">TOPIC DOSSIER</h3>
        <span class="hybrid-agenda-v6-panel-meta" data-fr27-type="meta">SOURCE-LINKED EVIDENCE</span>
      </header>

      <div class="hybrid-agenda-v6-panel-body hybrid-agenda-v6-dossier-body">
        <section class="hybrid-agenda-v6-identity">
          <span class="hybrid-agenda-v6-dossier-icon" aria-hidden="true">
            ${agendaTopicIcon(topic.id)}
          </span>

          <div class="hybrid-agenda-v6-identity-copy">
            <span class="hybrid-agenda-v6-kicker" data-fr27-type="kicker">SELECTED RECURRING TOPIC</span>

            <div class="hybrid-agenda-v6-title-line">
              <h4 data-fr27-type="item-title">${escapeHtml(topic.label)}</h4>

              <span
                class="hybrid-agenda-v6-badge"
                data-movement="${escapeAttribute(movement)}"
                data-fr27-type="status-label"
              >${escapeHtml(topic.movement)}</span>

              <span class="hybrid-agenda-v6-badge is-structure" data-fr27-type="status-label">
                ${escapeHtml(topic.structure)}
              </span>
            </div>
          </div>
        </section>

        <section
          class="hybrid-agenda-v6-metrics"
          aria-label="Selected topic headline metrics"
        >
          <article>
            <strong data-fr27-type="key-data">${topic.source_day_count}</strong>
            <span data-fr27-type="field-label">30D SOURCE-DAYS</span>
          </article>

          <article>
            <strong data-movement="${escapeAttribute(movement)}" data-fr27-type="key-data">
              ${escapeHtml(agendaSignedPp(topic.agendaShareChangePp))}
            </strong>
            <span data-fr27-type="field-label">AGENDA SHARE Δ</span>
          </article>

          <article>
            <strong data-fr27-type="key-data">${topic.publisher_count}</strong>
            <span data-fr27-type="field-label">PUBLISHERS</span>
          </article>
        </section>

        ${renderAgendaV6Activity(topic, model.evolution)}

        <div class="hybrid-agenda-v6-detail-grid">
          <section class="hybrid-agenda-v6-detail-card">
            <div class="hybrid-agenda-v6-detail-head">
              <strong data-fr27-type="module-title">ASSOCIATED SIGNALS</strong>
              <span data-fr27-type="meta">${signalHits} hits · ${signalCount} signals</span>
            </div>
            ${renderAgendaV6Signals(topic)}
          </section>

          <section class="hybrid-agenda-v6-detail-card">
            <div class="hybrid-agenda-v6-detail-head">
              <strong data-fr27-type="module-title">RECENT EVIDENCE</strong>
              <span data-fr27-type="meta">${Math.min(8, evidenceCount)} of ${evidenceCount}</span>
            </div>
            ${renderAgendaV6Evidence(topic)}
          </section>
        </div>
      </div>
    </section>`;
  }


  function policyIssueIcon(issueId) {
    const icons = {
      economy_public_finances: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <path d="M3 14V8M7 14V5M11 14V9M15 14V3"/>
          <path d="M2 14.5h14"/>
        </svg>`,

      work_purchasing_power_pensions: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <rect x="3" y="6" width="12" height="8" rx="1"/>
          <path d="M6.5 6V4h5v2M3 9h12"/>
        </svg>`,

      immigration_identity_secularism: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <path d="M3 9h9M9 5l4 4-4 4"/>
          <path d="M15 3v12"/>
        </svg>`,

      security_justice: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <path d="M9 2.5 14 5v4c0 3-1.9 5.1-5 6.5C5.9 14.1 4 12 4 9V5l5-2.5Z"/>
          <path d="M6.5 9 8.3 11 12 6.8"/>
        </svg>`,

      health_education_public_services: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <path d="M9 3v12M3 9h12"/>
        </svg>`,

      climate_energy_agriculture: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <path d="M14.5 3.5C9 3.7 5.5 6.2 4.5 11.5"/>
          <path d="M4 14c2-4 5-6.5 9.5-8"/>
          <path d="M9 11c1.5 1 3 1.4 4.7 1.2"/>
        </svg>`,

      europe_defence_foreign_affairs: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <circle cx="9" cy="9" r="6"/>
          <path d="M3.5 9h11M9 3c1.7 1.8 2.5 3.8 2.5 6S10.7 13.2 9 15M9 3C7.3 4.8 6.5 6.8 6.5 9S7.3 13.2 9 15"/>
        </svg>`,

      institutions_democracy_territories: `
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <path d="M3 7h12M4 7l5-4 5 4"/>
          <path d="M5 7v6M9 7v6M13 7v6M3 14h12"/>
        </svg>`
    };

    return icons[issueId] || `
      <svg viewBox="0 0 18 18" aria-hidden="true">
        <circle cx="9" cy="9" r="5.5"/>
      </svg>`;
  }

  function renderIssuesMonitor(model) {
    const diagnostics =
      model.diagnostics;

    const selected =
      model.selectedIssue;

    const maximumSourceDays =
      Math.max(
        1,
        ...model.topics.map(
          topic =>
            number(
              topic.source_day_count
            )
        )
      );

    const rows =
      model.topics
        .map(topic => {
          const selectedRow =
            topic.id ===
            selected?.id;

          const movement =
            String(
              topic.movement ||
              "STABLE"
            ).toLowerCase();

          const glyph =
            movement === "rising"
              ? "▲"
              : movement === "fading"
                ? "▼"
                : "•";

          const width =
            Math.max(
              4,
              number(
                topic.source_day_count
              ) /
                maximumSourceDays *
                100
            );

          return `<button
            class="hybrid-agenda-v6-topic-card"
            type="button"
            data-hybrid-policy-issue="${escapeAttribute(topic.id)}"
            data-movement="${escapeAttribute(movement)}"
            aria-pressed="${String(selectedRow)}"
          >
            <span
              class="hybrid-agenda-v6-topic-icon"
              aria-hidden="true"
            >
              ${policyIssueIcon(topic.id)}
            </span>

            <span class="hybrid-agenda-v6-topic-copy">
              <span class="hybrid-agenda-v6-topic-name" data-fr27-type="item-title">
                ${escapeHtml(topic.label)}
              </span>

              <span class="hybrid-agenda-v6-topic-tags">
                <span
                  class="hybrid-agenda-v6-badge"
                  data-movement="${escapeAttribute(movement)}"
                  data-fr27-type="status-label"
                >
                  ${escapeHtml(topic.movement)}
                </span>

                <span class="hybrid-agenda-v6-badge is-structure" data-fr27-type="status-label">
                  ${escapeHtml(topic.structure)}
                </span>
              </span>
            </span>

            <span class="hybrid-agenda-v6-topic-total">
              <strong data-fr27-type="data">${topic.source_day_count}</strong>
              <span data-fr27-type="field-label">SOURCE-DAYS</span>

              <i
                class="hybrid-agenda-v6-topic-volume"
                aria-hidden="true"
              >
                <b
                  style="--agenda-monitor-volume:${width.toFixed(1)}%"
                ></b>
              </i>
            </span>

            <span class="hybrid-agenda-v6-topic-shift">
              <span>
                <small data-fr27-type="field-label">PRIOR</small>
                <strong data-fr27-type="data">${topic.previousIncidence.toFixed(1)}%</strong>
              </span>

              <span>
                <small data-fr27-type="field-label">LATEST</small>
                <strong data-fr27-type="data">${topic.latestIncidence.toFixed(1)}%</strong>
              </span>

              <em
                data-movement="${escapeAttribute(movement)}"
                data-fr27-type="data"
              >
                ${glyph}
                ${escapeHtml(
                  agendaSignedPp(
                    topic.incidenceChangePp
                  )
                )}
              </em>
            </span>
          </button>`;
        })
        .join("");

    return `<section
      class="hybrid-agenda-v6-panel hybrid-agenda-v6-monitor"
    >
      <header class="hybrid-agenda-v6-panel-head">
        <h3 class="hybrid-agenda-v6-panel-title" data-fr27-type="panel-title">
          POLICY MONITOR
        </h3>

        <span class="hybrid-agenda-v6-panel-meta" data-fr27-type="meta">
          ${model.topics.length}
          ISSUES · 30D
        </span>
      </header>

      <div
        class="hybrid-agenda-v6-panel-body hybrid-agenda-v6-monitor-body"
      >
        <div
          class="hybrid-agenda-v6-diagnostics"
          aria-label="Policy issue diagnostics"
        >
          <article class="is-active">
            <span data-fr27-type="field-label">ACTIVE 7D</span>
            <strong data-fr27-type="key-data">
              ${diagnostics.activeIssues}
            </strong>
          </article>

          <article class="is-concentration">
            <span data-fr27-type="field-label">LEADING ISSUE</span>
            <strong class="hybrid-issues-leading" data-fr27-type="key-data">
              ${escapeHtml(
                policyIssueCode(
                  diagnostics.leadingIssue
                )
              )}
            </strong>
          </article>

          <article class="is-rising">
            <span data-fr27-type="field-label">RISING ISSUES</span>
            <strong data-fr27-type="key-data">
              ${diagnostics.risingIssues}
            </strong>
          </article>

          <article class="is-turnover">
            <span data-fr27-type="field-label">POLICY COVERAGE</span>
            <strong data-fr27-type="key-data">
              ${diagnostics.policyCoverage.toFixed(1)}%
            </strong>
          </article>
        </div>

        <div class="hybrid-agenda-v6-topic-list">
          ${rows}
        </div>
      </div>
    </section>`;
  }

  function renderIssuesMatrix(model) {
    const periodHeaders =
      model.evolutionBins
        .map(
          bin => `
            <span class="hybrid-agenda-v6-period" data-fr27-type="scale-label">
              ${escapeHtml(
                agendaPeriodLabel(
                  bin.start,
                  bin.end
                )
              )}
            </span>
          `
        )
        .join("");

    const rows =
      model.topics
        .map(topic => `
          <button
            class="hybrid-agenda-v6-matrix-row"
            type="button"
            data-hybrid-policy-issue="${escapeAttribute(topic.id)}"
            aria-pressed="${String(topic.id === model.selectedIssue?.id)}"
            data-fr27-tooltip="${escapeAttribute(topic.label)}"
          >
            <span class="hybrid-agenda-v6-matrix-label" data-fr27-type="row-label">
              ${escapeHtml(
                policyIssueShortLabel(topic)
              )}
            </span>

            ${topic.daily_activity
              .map(
                (day, index) =>
                  agendaDailyCellV6(
                    day,
                    index,
                    model.heatmapMaxSourceDays,
                    model.evolution
                  )
              )
              .join("")}

            <strong class="hybrid-agenda-v6-matrix-total" data-fr27-type="data">
              ${topic.source_day_count}
            </strong>
          </button>
        `)
        .join("");

    return `<section
      class="hybrid-agenda-v6-module hybrid-agenda-v6-matrix-module"
    >
      <div class="hybrid-agenda-v6-module-head">
        <strong data-fr27-type="module-title">30-DAY EVOLUTION</strong>

        <span data-fr27-type="scale-label">
          ${escapeHtml(
            agendaCompactDate(
              model.evolution.period_start
            )
          )}
          →
          ${escapeHtml(
            agendaCompactDate(
              model.evolution.period_end
            )
          )}
        </span>
      </div>

      <div class="hybrid-agenda-v6-matrix-wrap">
        <div
          class="hybrid-agenda-v6-matrix"
          role="group"
          aria-label="Thirty-day Policy Issues evolution matrix"
        >
          <div
            class="hybrid-agenda-v6-matrix-head"
            aria-hidden="true"
          >
            <span data-fr27-type="field-label">ISSUE</span>
            ${periodHeaders}
            <span data-fr27-type="scale-label">30D</span>
          </div>

          ${rows}
        </div>

        <div
          class="hybrid-agenda-v6-matrix-legend"
          aria-label="Policy Issues evolution color key"
        >
          <span data-fr27-type="scale-label"><i data-window="older"></i>OLDER</span>
          <span data-fr27-type="scale-label"><i data-window="previous"></i>PRIOR 7D</span>
          <span data-fr27-type="scale-label"><i data-window="latest"></i>LATEST 7D</span>
          <span data-fr27-type="scale-label"><i data-window="partial"></i>PARTIAL DAY</span>
        </div>
      </div>
    </section>`;
  }

  function renderIssuesWeekShift(model) {
    const maximum =
      Math.max(
        1,
        ...model.topics.flatMap(
          topic => [
            number(
              topic.previousIncidence
            ),
            number(
              topic.latestIncidence
            )
          ]
        )
      );

    const rows =
      model.topics
        .map(topic => {
          const previous =
            number(
              topic.previousIncidence
            );

          const latest =
            number(
              topic.latestIncidence
            );

          const movement =
            String(
              topic.movement ||
              "STABLE"
            ).toLowerCase();

          const glyph =
            movement === "rising"
              ? "▲"
              : movement === "fading"
                ? "▼"
                : "•";

          return `<div
            class="hybrid-agenda-v6-shift-row"
            data-movement="${escapeAttribute(movement)}"
          >
            <span class="hybrid-agenda-v6-shift-label" data-fr27-type="row-label">
              ${escapeHtml(
                policyIssueShortLabel(topic)
              )}
            </span>

            <span
              class="hybrid-agenda-v6-pair-bars"
              aria-label="Prior ${previous.toFixed(1)} percent; latest ${latest.toFixed(1)} percent issue incidence"
            >
              <span
                class="hybrid-agenda-v6-pair-track is-prior"
                aria-hidden="true"
              >
                <i
                  style="--agenda-width:${(previous / maximum * 100).toFixed(1)}%"
                ></i>
              </span>

              <span
                class="hybrid-agenda-v6-pair-track is-latest"
                aria-hidden="true"
              >
                <i
                  style="--agenda-width:${(latest / maximum * 100).toFixed(1)}%"
                ></i>
              </span>
            </span>

            <span class="hybrid-agenda-v6-shift-count" data-fr27-type="data">
              ${previous.toFixed(1)}%
              →
              ${latest.toFixed(1)}%
            </span>

            <strong
              class="hybrid-agenda-v6-shift-delta"
              data-movement="${escapeAttribute(movement)}"
              data-fr27-type="data"
            >
              ${glyph}
              ${escapeHtml(
                agendaSignedPp(
                  topic.incidenceChangePp
                )
              )}
            </strong>
          </div>`;
        })
        .join("");

    return `<section
      class="hybrid-agenda-v6-module hybrid-agenda-v6-shift-module"
    >
      <div class="hybrid-agenda-v6-module-head">
        <strong data-fr27-type="module-title">WEEK SHIFT</strong>

        <span class="hybrid-agenda-v6-shift-key" data-fr27-type="scale-label">
          <span>
            <i class="is-prior" aria-hidden="true"></i>
            PRIOR
          </span>

          <span>
            <i class="is-latest" aria-hidden="true"></i>
            LATEST
          </span>
        </span>
      </div>

      <div class="hybrid-agenda-v6-shift-list">
        ${rows}
      </div>
    </section>`;
  }

  function renderIssuesAnalysis(model) {
    return `<section
      class="hybrid-agenda-v6-panel hybrid-agenda-v6-evolution-panel"
    >
      <header class="hybrid-agenda-v6-panel-head">
        <h3 data-fr27-type="panel-title">ISSUE EVOLUTION</h3>

        <span class="hybrid-agenda-v6-head-tools">
          <span class="hybrid-agenda-v6-panel-head-meta" data-fr27-type="meta">
            COMPLETE-WEEK COMPARISON
          </span>

          <button
            class="hybrid-agenda-v6-info fr27-info-glyph"
            type="button"
            aria-label="Policy Issues methodology"
            data-fr27-tooltip="Deterministic multi-label classification of accepted presidential coverage. Source-day = unique publisher × UTC date. Issue incidence = issue source-days divided by all accepted presidential-coverage source-days in the same complete week. Percentages can overlap and need not total 100%. This measures monitored media coverage, not voter priorities."
          >
            <span aria-hidden="true">i</span>
          </button>
        </span>
      </header>

      <div
        class="hybrid-agenda-v6-panel-body hybrid-agenda-v6-evolution-body"
      >
        ${renderIssuesMatrix(model)}
        ${renderIssuesWeekShift(model)}
      </div>
    </section>`;
  }

  function renderIssueCandidates(topic) {
    const candidates =
      Array.isArray(
        topic.candidate_counts
      )
        ? topic.candidate_counts
            .slice(0, 8)
        : [];

    if (!candidates.length) {
      return `<div
        class="hybrid-agenda-v6-scroll"
        data-agenda-scroll-region="issue-candidates"
      >
        <div class="hybrid-agenda-v6-empty">
          No candidate association is supported by the selected issue evidence.
        </div>
      </div>`;
    }

    const maximum =
      Math.max(
        1,
        ...candidates.map(
          item =>
            number(
              item.item_count
            )
        )
      );

    return `<div
      class="hybrid-agenda-v6-scroll"
      data-agenda-scroll-region="issue-candidates"
    >
      <div class="hybrid-agenda-v6-signal-list">
        ${candidates
          .map(item => {
            const count =
              number(
                item.item_count
              );

            return `<div
              class="hybrid-agenda-v6-signal-item"
            >
              <div class="hybrid-agenda-v6-signal-head">
                <span data-fr27-type="row-label">
                  ${escapeHtml(
                    item.candidate
                  )}
                </span>

                <strong data-fr27-type="data">
                  ${count}
                </strong>
              </div>

              <span
                class="hybrid-agenda-v6-signal-track"
                aria-hidden="true"
              >
                <i
                  style="--agenda-signal-width:${(count / maximum * 100).toFixed(1)}%"
                ></i>
              </span>
            </div>`;
          })
          .join("")}
      </div>
    </div>`;
  }

  function renderIssueSubtopicBadge(topic) {
    const lead =
      Array.isArray(
        topic.subtopic_counts
      )
        ? topic.subtopic_counts[0]
        : null;

    if (!lead) return "";

    return `<span
      class="hybrid-agenda-v6-badge is-structure"
      data-fr27-type="status-label"
      data-fr27-tooltip="${escapeAttribute(
        `${policySubtopicLabel(lead.id)} · ${lead.item_count} matched articles`
      )}"
      tabindex="0"
    >
      ${escapeHtml(
        policySubtopicLabel(
          lead.id
        )
      )}
    </span>`;
  }

  function renderIssuesDossier(model) {
    const topic =
      model.selectedIssue;

    if (!topic) return "";

    const movement =
      String(
        topic.movement ||
        "STABLE"
      ).toLowerCase();

    const evidenceCount =
      Array.isArray(
        topic.supporting_items
      )
        ? topic.supporting_items.length
        : 0;

    const candidateHits =
      topic.candidate_counts
        .reduce(
          (total, item) =>
            total +
            number(
              item.item_count
            ),
          0
        );

    return `<section
      class="hybrid-agenda-v6-panel hybrid-agenda-v6-dossier"
    >
      <header class="hybrid-agenda-v6-panel-head">
        <h3 class="hybrid-agenda-v6-panel-title" data-fr27-type="panel-title">
          ISSUE DOSSIER
        </h3>

        <span class="hybrid-agenda-v6-panel-meta" data-fr27-type="meta">
          SOURCE-LINKED EVIDENCE
        </span>
      </header>

      <div
        class="hybrid-agenda-v6-panel-body hybrid-agenda-v6-dossier-body"
      >
        <section class="hybrid-agenda-v6-identity">
          <span
            class="hybrid-agenda-v6-dossier-icon"
            aria-hidden="true"
          >
            ${policyIssueIcon(topic.id)}
          </span>

          <div class="hybrid-agenda-v6-identity-copy">
            <span class="hybrid-agenda-v6-kicker" data-fr27-type="kicker">
              SELECTED SUBSTANTIVE ISSUE
            </span>

            <div class="hybrid-agenda-v6-title-line">
              <h4 data-fr27-type="item-title">
                ${escapeHtml(topic.label)}
              </h4>

              <span
                class="hybrid-agenda-v6-badge"
                data-movement="${escapeAttribute(movement)}"
                data-fr27-type="status-label"
              >
                ${escapeHtml(
                  topic.movement
                )}
              </span>

              ${renderIssueSubtopicBadge(topic)}
            </div>
          </div>
        </section>

        <section
          class="hybrid-agenda-v6-metrics"
          aria-label="Selected issue headline metrics"
        >
          <article>
            <strong data-fr27-type="key-data">
              ${topic.source_day_count}
            </strong>
            <span data-fr27-type="field-label">30D SOURCE-DAYS</span>
          </article>

          <article>
            <strong data-fr27-type="key-data">
              ${topic.latestIncidence.toFixed(1)}%
            </strong>
            <span data-fr27-type="field-label">7D INCIDENCE</span>
          </article>

          <article>
            <strong
              data-movement="${escapeAttribute(movement)}"
              data-fr27-type="key-data"
            >
              ${escapeHtml(
                agendaSignedPp(
                  topic.incidenceChangePp
                )
              )}
            </strong>
            <span data-fr27-type="field-label">INCIDENCE Δ</span>
          </article>
        </section>

        ${renderAgendaV6Activity(
          topic,
          model.evolution
        )}

        <div class="hybrid-agenda-v6-detail-grid">
          <section class="hybrid-agenda-v6-detail-card">
            <div class="hybrid-agenda-v6-detail-head">
              <strong data-fr27-type="module-title">
                CANDIDATE ASSOCIATIONS
              </strong>

              <span data-fr27-type="meta">
                ${candidateHits}
                hits ·
                ${topic.candidate_counts.length}
                candidates
              </span>
            </div>

            ${renderIssueCandidates(topic)}
          </section>

          <section class="hybrid-agenda-v6-detail-card">
            <div class="hybrid-agenda-v6-detail-head">
              <strong data-fr27-type="module-title">
                RECENT EVIDENCE
              </strong>

              <span data-fr27-type="meta">
                ${Math.min(
                  8,
                  evidenceCount
                )}
                of
                ${evidenceCount}
              </span>
            </div>

            ${renderAgendaV6Evidence(topic)}
          </section>
        </div>
      </div>
    </section>`;
  }

  function renderIssuesPanel(model) {
    if (
      model.state !== "ready"
    ) {
      if (model.state === "loading" && window.FR27UI) {
        return window.FR27UI.skeletonElement(
          "issues",
          "Loading policy issues"
        ).outerHTML;
      }
      return summaryState(model);
    }

    return `<div
      class="hybrid-agenda-v6-workspace"
      aria-label="Policy Issues analytical workspace"
    >
      ${renderIssuesMonitor(model)}
      ${renderIssuesAnalysis(model)}
      ${renderIssuesDossier(model)}
    </div>`;
  }

  function renderAgendaPanel(model) {
    if (model.state !== "ready") {
      if (model.state === "loading" && window.FR27UI) {
        return window.FR27UI.skeletonElement(
          "agenda",
          "Loading campaign agenda"
        ).outerHTML;
      }
      return summaryState(model);
    }

    if (!model.evolutionReady) {
      return renderLegacyAgendaPanel(model);
    }

    return `<div class="hybrid-agenda-v6-workspace">
      ${renderAgendaV6Monitor(model)}
      ${renderAgendaV6Analysis(model)}
      ${renderAgendaV6Dossier(model)}
    </div>`;
  }

  function campaignEventTypeLabel(value) {
    const labels = {
      rally: "RALLY",
      debate: "DEBATE",
      candidate_visit: "CANDIDATE VISIT",
      campaign_launch: "CAMPAIGN LAUNCH",
      media_appearance: "MEDIA APPEARANCE",
      press_conference: "PRESS CONFERENCE",
      public_meeting: "PUBLIC MEETING",
      speech: "SPEECH",
      party_event: "PARTY EVENT",
      primary: "PRIMARY",
      candidacy_announcement: "CANDIDACY ANNOUNCEMENT",
      program_launch: "PROGRAM LAUNCH",
      other: "OTHER",
      first_round: "FIRST ROUND",
      second_round: "SECOND ROUND"
    };

    return labels[value] ||
      String(value || "EVENT")
        .replaceAll("_", " ")
        .toUpperCase();
  }

  function campaignEventTypeDisplayLabel(value) {
    return campaignEventTypeLabel(value)
      .split(/\s+/)
      .filter(Boolean)
      .map(word => word.charAt(0) + word.slice(1).toLowerCase())
      .join(" ");
  }

  function campaignEventTypeCode(value) {
    const codes = {
      rally: "RL",
      debate: "DB",
      candidate_visit: "VS",
      campaign_launch: "LN",
      media_appearance: "MD",
      press_conference: "PC",
      public_meeting: "MT",
      speech: "SP",
      party_event: "PT",
      primary: "PR",
      candidacy_announcement: "CA",
      program_launch: "PG",
      other: "OT",
      first_round: "1R",
      second_round: "2R"
    };
    return codes[value] || "EV";
  }

  function campaignEventStatusPresentation(event) {
    if (
      event.status === "scheduled" &&
      event.evidence_status === "past_unconfirmed"
    ) {
      return {
        key: "unconfirmed",
        label: "PAST · UNCONFIRMED"
      };
    }

    const labels = {
      scheduled: "SCHEDULED",
      postponed: "POSTPONED",
      cancelled: "CANCELLED",
      completed: "COMPLETED"
    };

    return {
      key: event.status || "unknown",
      label: labels[event.status] || "STATUS UNKNOWN"
    };
  }

  function campaignEventEvidencePresentation(event) {
    if (event?.evidence_status === "verified") {
      return { key: "verified", label: "VERIFIED" };
    }
    if (event?.evidence_status === "past_unconfirmed") {
      return { key: "unconfirmed", label: "UNCONFIRMED" };
    }
    const raw = String(event?.evidence_status || "evidence unknown");
    return {
      key: raw.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
      label: raw.replaceAll("_", " ").toUpperCase()
    };
  }

  function campaignEventTimeLabel(event) {
    if (event.time_precision !== "datetime") {
      return "—";
    }

    const date = new Date(event.scheduled_start);
    if (!Number.isFinite(date.getTime())) {
      return "—";
    }

    return new Intl.DateTimeFormat(
      "en-GB",
      {
        timeZone: "Europe/Paris",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23"
      }
    ).format(date);
  }

  function campaignEventObservedLabel(value) {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) {
      return "DATE UNAVAILABLE";
    }

    return new Intl.DateTimeFormat(
      "en-GB",
      {
        timeZone: "Europe/Paris",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23"
      }
    )
      .format(date)
      .replace(",", " · ")
      .toUpperCase();
  }

  function campaignEventPeopleLabel(event) {
    const candidateNames = Array.isArray(event.candidate_names)
      ? event.candidate_names.filter(Boolean)
      : [];
    const participants = Array.isArray(event.participants)
      ? event.participants.filter(Boolean)
      : [];

    const people = candidateNames.length
      ? candidateNames
      : participants;

    if (people.length) {
      return people.join(", ");
    }

    return String(event.organization || "").trim();
  }

  function campaignEventCompactPeopleLabel(event) {
    const candidateNames = Array.isArray(event.candidate_names)
      ? event.candidate_names.filter(Boolean)
      : [];
    if (candidateNames.length > 2) {
      return `${candidateNames.slice(0, 2).join(", ")} +${candidateNames.length - 2}`;
    }
    if (candidateNames.length) return candidateNames.join(", ");
    return String(event.organization || "").trim();
  }

  function campaignEventPlaceLabel(event) {
    const values = [
      event.location_name,
      event.locality,
      event.department
        ? `DEP. ${event.department}`
        : ""
    ]
      .map(value => String(value || "").trim())
      .filter(Boolean);

    return [...new Set(values)].join(" · ");
  }

  function campaignEventPrimaryEvidence(record) {
    return Array.isArray(record?.evidence)
      ? record.evidence[0] || null
      : null;
  }

  function campaignEventDisplayDate(value) {
    const raw = String(value || "");
    const dateOnly = campaignEventDateFromKey(raw);
    if (dateOnly) {
      return { date: dateOnly, timeZone: "UTC" };
    }
    const date = new Date(raw);
    return Number.isFinite(date.getTime())
      ? { date, timeZone: "Europe/Paris" }
      : null;
  }

  function campaignEventShortDate(value) {
    const parsed = campaignEventDisplayDate(value);
    if (!parsed) return "DATE UNAVAILABLE";
    return new Intl.DateTimeFormat(
      "en-GB",
      {
        timeZone: parsed.timeZone,
        day: "2-digit",
        month: "short"
      }
    ).format(parsed.date).toUpperCase();
  }

  function campaignEventLongDate(value) {
    const parsed = campaignEventDisplayDate(value);
    if (!parsed) return "DATE UNAVAILABLE";
    return new Intl.DateTimeFormat(
      "en-GB",
      {
        timeZone: parsed.timeZone,
        day: "2-digit",
        month: "short",
        year: "numeric"
      }
    ).format(parsed.date).toUpperCase();
  }

  function campaignEventSourceTypeLabel(value) {
    const labels = {
      reliable_media: "RELIABLE MEDIA",
      organizer_first_party: "ORGANISER FIRST-PARTY",
      candidate_first_party: "CANDIDATE FIRST-PARTY",
      party_first_party: "PARTY FIRST-PARTY",
      official_unstructured: "OFFICIAL SOURCE"
    };
    return labels[value] || String(value || "SOURCE").replaceAll("_", " ").toUpperCase();
  }

  function campaignEventEvidenceTypeLabel(value) {
    const labels = {
      explicit_schedule: "Explicit schedule published",
      official_rule_derivation: "Official calendar derivation"
    };
    return labels[value] || String(value || "Evidence published").replaceAll("_", " ");
  }

  function campaignEventParticipantCount(event) {
    const candidates = Array.isArray(event?.candidate_names)
      ? event.candidate_names.filter(Boolean)
      : [];
    if (candidates.length) return candidates.length;
    const participants = Array.isArray(event?.participants)
      ? event.participants.filter(Boolean)
      : [];
    return participants.length;
  }

  function campaignEventInvolvementLabel(event) {
    const candidates = Array.isArray(event?.candidate_names)
      ? event.candidate_names.filter(Boolean)
      : [];
    if (candidates.length > 1) return `${candidates.length} CANDIDATES`;
    if (candidates.length === 1) return "SOLO";

    const participants = Array.isArray(event?.participants)
      ? event.participants.filter(Boolean)
      : [];
    if (participants.length > 1) return `${participants.length} PARTICIPANTS`;
    if (participants.length === 1) return "SOLO";
    return "COLLECTIVE";
  }

  function campaignEventUpdateCopy(update) {
    const evidence = campaignEventPrimaryEvidence(update);
    const publisher = String(evidence?.source_publisher || "source").trim();
    const type = String(update.update_type || "UPDATED").toUpperCase();
    if (type === "NEW") return `Event added from ${publisher}`;
    if (type === "CONFIRMED") return `Schedule confirmation published by ${publisher}`;
    if (type === "POSTPONED") return `Postponement published by ${publisher}`;
    if (type === "CANCELLED") return `Cancellation published by ${publisher}`;
    return update.headline || `Calendar update published by ${publisher}`;
  }

  function campaignEventWeekdayLabel(value) {
    const parsed = campaignEventDisplayDate(value);
    if (!parsed) return "";
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: parsed.timeZone,
      weekday: "short"
    }).format(parsed.date).toUpperCase();
  }

  function renderEventTypeBadge(eventType, extra = "") {
    return `<span class="hybrid-events-type-badge" data-fr27-type="status-label" data-event-type="${escapeAttribute(eventType)}">
      <strong>${escapeHtml(campaignEventTypeCode(eventType))}</strong>
      ${extra ? `<small>${escapeHtml(extra)}</small>` : ""}
    </span>`;
  }

  function campaignEventRelativeAgeLabel(value, now = new Date()) {
    const date = new Date(String(value || ""));
    if (!Number.isFinite(date.getTime())) return "—";
    const diffMs = Math.max(0, now.getTime() - date.getTime());
    const minutes = Math.floor(diffMs / 60000);
    if (minutes < 60) return `${Math.max(1, minutes)}M AGO`;
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return `${hours}H AGO`;
    return `${Math.floor(hours / 24)}D AGO`;
  }

  const campaignEventHorizonCategories = [
    {
      key: "debate",
      label: "DEBATE",
      types: ["debate"]
    },
    {
      key: "rally",
      label: "RALLY / MEETING",
      types: ["rally", "public_meeting", "speech"]
    },
    {
      key: "visit",
      label: "VISIT",
      types: ["candidate_visit"]
    },
    {
      key: "launch",
      label: "LAUNCH / ANNOUNCEMENT",
      types: ["campaign_launch", "candidacy_announcement", "program_launch", "primary"]
    },
    {
      key: "media",
      label: "INTERVIEW / MEDIA",
      types: ["media_appearance"]
    },
    {
      key: "other",
      label: "PRESS CONF. / OTHER",
      types: ["press_conference", "party_event", "other"]
    }
  ];

  function campaignEventHorizonCategory(eventType) {
    return campaignEventHorizonCategories.find(category =>
      category.types.includes(eventType)
    ) || campaignEventHorizonCategories[campaignEventHorizonCategories.length - 1];
  }

  function campaignEventMatchesTypeFilter(event, filterKey) {
    if (!filterKey || filterKey === "all") return true;
    return campaignEventHorizonCategory(event.event_type).key === filterKey;
  }

  function campaignEventFilterOptions(model) {
    const present = new Set(
      model.upcomingEvents.map(event =>
        campaignEventHorizonCategory(event.event_type).key
      )
    );
    return [
      { key: "all", label: "ALL" },
      ...campaignEventHorizonCategories
        .filter(category => present.has(category.key))
        .map(category => ({
          key: category.key,
          label: campaignEventHorizonCategoryLabel(category.key)
        }))
    ];
  }

  function campaignEventLatestMaterialUpdate(event, model) {
    return model.eventWatch.find(update =>
      update.event_id === event.event_id &&
      String(update.update_type || "").toUpperCase() !== "NEW"
    ) || null;
  }

  function campaignEventStreamRightLabel(event, model) {
    const materialUpdate = campaignEventLatestMaterialUpdate(event, model);
    if (materialUpdate) return String(materialUpdate.update_type || "UPDATED").toUpperCase();
    const participantCount = campaignEventParticipantCount(event);
    if (participantCount > 1) return `${participantCount} PARTICIPANTS`;
    const status = campaignEventStatusPresentation(event);
    if (status.key !== "scheduled") return status.label;
    const evidenceState = campaignEventEvidencePresentation(event);
    if (evidenceState.key !== "verified") return evidenceState.label;
    return "";
  }

  function buildCampaignEventStreamGroups(events) {
    const groups = new Map();
    events.forEach(event => {
      const startKey = campaignEventWeekStartKey(campaignEventDateKey(event));
      const endKey = campaignEventOffsetDateKey(startKey, 6);
      if (!groups.has(startKey)) {
        groups.set(startKey, {
          startKey,
          endKey,
          label: campaignEventWeekRangeLabel(startKey, endKey),
          events: []
        });
      }
      groups.get(startKey).events.push(event);
    });
    return [...groups.values()].sort((a, b) => a.startKey.localeCompare(b.startKey));
  }

  function campaignEventWatchCounts(eventWatch) {
    const counts = {
      NEW: 0,
      CONFIRMED: 0,
      UPDATED: 0,
      POSTPONED: 0,
      CANCELLED: 0
    };
    eventWatch.forEach(update => {
      const key = String(update.update_type || "UPDATED").toUpperCase();
      if (Object.prototype.hasOwnProperty.call(counts, key)) counts[key] += 1;
    });
    return counts;
  }

  function campaignEventObservedParts(value) {
    const label = campaignEventObservedLabel(value);
    const pieces = label.split(" · ");
    if (pieces.length > 1) {
      return {
        date: pieces.slice(0, -1).join(" · "),
        time: pieces[pieces.length - 1]
      };
    }
    return { date: label, time: "" };
  }

  function campaignEventObservedMinuteKey(value) {
    const date = new Date(String(value || ""));
    return Number.isFinite(date.getTime())
      ? date.toISOString().slice(0, 16)
      : String(value || "DATE UNAVAILABLE");
  }

  function groupCampaignEventAdditions(eventWatch) {
    const groups = new Map();
    eventWatch
      .filter(update => String(update.update_type || "").toUpperCase() === "NEW")
      .forEach(update => {
        const key = campaignEventObservedMinuteKey(update.observed_at);
        if (!groups.has(key)) {
          groups.set(key, { key, observedAt: update.observed_at, updates: [] });
        }
        groups.get(key).updates.push(update);
      });
    return [...groups.values()];
  }

  function campaignEventHorizonCategoryLabel(key) {
    const labels = {
      debate: "DEBATE",
      rally: "RALLY / MEETING",
      visit: "VISIT",
      launch: "LAUNCH",
      media: "MEDIA",
      other: "OTHER"
    };
    return labels[key] || "OTHER";
  }

  const campaignEventHorizonDotCategories = [
    { key: "debate", eventType: "debate", label: "DEBATE", horizonKeys: ["debate"] },
    { key: "rally", eventType: "rally", label: "RALLY / MEETING", horizonKeys: ["rally"] },
    { key: "visit", eventType: "candidate_visit", label: "VISIT", horizonKeys: ["visit"] },
    { key: "launch", eventType: "campaign_launch", label: "LAUNCH", horizonKeys: ["launch"] },
    { key: "other", eventType: "other", label: "OTHER", horizonKeys: ["media", "other"] }
  ];

  function campaignEventHorizonTypeGroups(events) {
    return campaignEventHorizonDotCategories
      .map(category => {
        const count = events.filter(event =>
          category.horizonKeys.includes(
            campaignEventHorizonCategory(event.event_type).key
          )
        ).length;
        return count ? {
          key: category.key,
          eventType: category.eventType,
          count,
          label: category.label
        } : null;
      })
      .filter(Boolean);
  }

  function renderOperationsHorizonComposition(events) {
    return campaignEventHorizonTypeGroups(events).map(group => `<span
      class="hybrid-events-ops-marker is-type-presence"
      data-event-type="${escapeAttribute(group.eventType)}"
      aria-hidden="true"
    ></span>`).join("");
  }

  function renderOperationsHorizonLegend(model) {
    const legendCategories = ["debate", "rally", "visit", "launch", "other"]
      .map(key => campaignEventHorizonCategories.find(category => category.key === key))
      .filter(Boolean);
    return `<footer class="hybrid-events-ops-legend" aria-label="Event type color legend"><div>${legendCategories.map(category => `<span class="hybrid-events-ops-legend-item"><i class="hybrid-events-ops-legend-swatch" data-event-type="${escapeAttribute(category.types[0])}" aria-hidden="true"></i><span data-fr27-type="status-label">${escapeHtml(campaignEventHorizonCategoryLabel(category.key))} [${escapeHtml(campaignEventTypeCode(category.types[0]))}]</span></span>`).join("")}</div><p data-fr27-type="body">Descriptive polling data from public sources · no model · no averages · no forecast · no voting advice.</p><p data-fr27-type="meta">Candidate portraits are AI-generated illustrations for visual identification.</p></footer>`;
  }

  function campaignEventScheduleMetricIcon(name) {
    const paths = {
      calendar: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M8 3v4M16 3v4M3.5 9.5h17"/>',
      clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>',
      people: '<circle cx="9" cy="8" r="2.6"/><circle cx="16.5" cy="9" r="2.1"/><path d="M3.5 19c.4-3.8 2.2-5.7 5.5-5.7s5.1 1.9 5.5 5.7M13 14c2.7-.2 4.6 1.4 5 5"/>'
    };
    const body = paths[name] || paths.calendar;
    return `<svg class="hybrid-events-ops-metric-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  }

  function renderOperationsScheduleRail(model) {
    const horizon = model.horizon;
    const monthStarts = new Set(horizon.monthGroups.map(group => group.start - 1));
    const months = horizon.monthGroups.map(group => `<span data-fr27-type="scale-label" style="grid-column:${group.start} / span ${group.span}">${escapeHtml(group.label)}</span>`).join("");
    const weeks = horizon.weekBins.map((bin, index) => {
      const selected = model.selectedWeek?.startKey === bin.startKey;
      const current = model.todayKey >= bin.startKey && model.todayKey <= bin.endKey;
      const monthStart = index > 0 && monthStarts.has(index);
      const countLabel = String(bin.count);
      const typeGroups = campaignEventHorizonTypeGroups(bin.events);
      const breakdown = typeGroups.length
        ? typeGroups.map(group => `${group.label}: ${group.count}`).join("; ")
        : "No scheduled events";
      const weekSummary = `${bin.label}. ${bin.count} scheduled ${bin.count === 1 ? "event" : "events"}. ${breakdown}.`;
      return `<div class="hybrid-events-ops-week${selected ? " is-selected" : ""}${current ? " is-current" : ""}${monthStart ? " is-month-start" : ""}">
        <button type="button" class="hybrid-events-ops-week-select" data-hybrid-week-select="${escapeAttribute(bin.startKey)}" aria-label="${escapeAttribute(`Navigate to week ${weekSummary}`)}" aria-pressed="${String(selected)}" data-fr27-tooltip="${escapeAttribute(weekSummary)}"${current ? ' aria-current="date"' : ""}>
          <span data-fr27-type="scale-label">${escapeHtml(bin.label)}</span><strong class="hybrid-events-ops-week-count${bin.count ? " has-events" : " is-empty"}" data-fr27-type="data">${escapeHtml(countLabel)}</strong>
        </button>
        <div class="hybrid-events-ops-week-markers" aria-hidden="true">${renderOperationsHorizonComposition(bin.events)}</div>
      </div>`;
    }).join("");
    const filters = campaignEventFilterOptions(model);
    const dataAsOf = campaignEventObservedLabel(model.dataAsOf);
    const scheduleInfo = `Curated high-signal calendar. Empty weeks do not imply no campaign activity. Past scheduled events are not treated as completed without explicit occurrence evidence. Data as of: ${dataAsOf}.`;

    return `<section class="hybrid-events-ops-rail" aria-labelledby="hybrid-events-ops-rail-title">
      <div class="hybrid-events-ops-rail-head">
        <div class="hybrid-events-ops-titleline">
          <h3 id="hybrid-events-ops-rail-title" data-fr27-type="panel-title">12-WEEK SCHEDULE</h3>
          <button class="hybrid-events-ops-info fr27-info-glyph" type="button" aria-label="Schedule methodology" data-fr27-tooltip="${escapeAttribute(scheduleInfo)}">i</button>
        </div>
        <div class="hybrid-events-ops-head-controls">
          <div class="hybrid-events-ops-filters" aria-label="Filter campaign events by type">${filters.map(filter => `<button type="button" class="hybrid-events-filter${model.eventTypeFilter === filter.key ? " is-active" : ""}" data-event-type="${escapeAttribute(filter.key)}" data-hybrid-events-filter="${escapeAttribute(filter.key)}" data-fr27-type="nav-label" aria-pressed="${String(model.eventTypeFilter === filter.key)}">${escapeHtml(filter.label)}</button>`).join("")}</div>
        </div>
      </div>
      <div class="hybrid-events-ops-horizon-scroll">
        <div class="hybrid-events-ops-horizon">
          <div class="hybrid-events-ops-months">${months}</div>
          <div class="hybrid-events-ops-weeks">${weeks}</div>
        </div>
      </div>
    </section>`;
  }

  function renderUpcomingEventRow(event, model, compact = false) {
    const selected = model.selectedEvent?.event_id === event.event_id;
    const participantCount = campaignEventParticipantCount(event);
    const people = campaignEventCompactPeopleLabel(event);
    const place = campaignEventPlaceLabel(event);
    const rightLabel = campaignEventStreamRightLabel(event, model);
    const dateParts = campaignEventShortDate(event.scheduled_start).split(" ");
    const weekday = campaignEventWeekdayLabel(event.scheduled_start);
    const weekStart = campaignEventWeekStartKey(campaignEventDateKey(event));

    return `<button
      class="hybrid-events-upcoming-row${selected ? " is-selected" : ""}${compact ? " is-compact" : ""}"
      type="button"
      data-event-type="${escapeAttribute(event.event_type)}"
      data-hybrid-event-id="${escapeAttribute(event.event_id)}"
      data-hybrid-event-week="${escapeAttribute(weekStart)}"
      aria-pressed="${String(selected)}"
    >
      <time data-fr27-type="scale-label" datetime="${escapeAttribute(event.scheduled_start)}"><strong>${escapeHtml(dateParts[0] || "")}</strong><span>${escapeHtml(dateParts.slice(1).join(" "))}</span><em>${escapeHtml(weekday)}</em></time>
      ${renderEventTypeBadge(event.event_type, participantCount > 1 ? `×${participantCount}` : "")}
      <span class="hybrid-events-upcoming-copy"><strong lang="fr" data-fr27-type="item-title">${escapeHtml(event.title)}</strong><small data-fr27-type="meta">${campaignEventTimeLabel(event) !== "—" ? `<b class="hybrid-events-upcoming-meta-time">${escapeHtml(campaignEventTimeLabel(event))}</b>` : ""}${campaignEventTimeLabel(event) !== "—" && (place || people) ? " · " : ""}${place ? escapeHtml(place) : ""}${place && people ? " · " : ""}${people ? escapeHtml(people) : ""}</small></span>
      ${rightLabel ? `<span class="hybrid-events-upcoming-right" data-fr27-type="status-label">${escapeHtml(rightLabel)}</span>` : ""}
    </button>`;
  }

  function renderUpcomingPanel(model) {
    const visible = model.filteredUpcomingEvents;
    const groups = buildCampaignEventStreamGroups(visible);
    const content = groups.length
      ? groups.map(group => `<section class="hybrid-events-upcoming-week" data-hybrid-event-week-group="${escapeAttribute(group.startKey)}">
          <div class="hybrid-events-upcoming-week-head"><strong data-fr27-type="scale-label">${escapeHtml(group.label)}</strong><span data-fr27-type="data">${group.events.length} ${group.events.length === 1 ? "EVENT" : "EVENTS"}</span></div>
          <div>${group.events.map(event => renderUpcomingEventRow(event, model)).join("")}</div>
        </section>`).join("")
      : '<div class="hybrid-state" data-fr27-type="status-label">No upcoming events match this event-type filter.</div>';
    const filteredMeta = model.eventTypeFilter === "all"
      ? `${model.upcomingCount} EVENTS`
      : `${visible.length} OF ${model.upcomingCount}`;

    return `<section class="hybrid-events-upcoming" aria-labelledby="hybrid-events-upcoming-title">
      <div class="hybrid-events-panel-head"><h3 id="hybrid-events-upcoming-title" data-fr27-type="panel-title">UPCOMING EVENTS</h3><span data-fr27-type="meta">${escapeHtml(filteredMeta)}</span></div>
      <div class="hybrid-events-upcoming-list">${content}</div>
    </section>`;
  }

  function renderDossierEventDetails(event) {
    const organizer = String(event.organization || "").trim() || "Not published";
    const precision = event.time_precision === "date" ? "Date only" : "Date + time";
    const format = campaignEventTypeDisplayLabel(event.event_type);
    return `<section class="hybrid-events-dossier-context"><h4 data-fr27-type="module-title">EVENT DETAILS</h4><dl>
      <div><dt data-fr27-type="field-label">Organiser</dt><dd data-fr27-type="meta">${escapeHtml(organizer)}</dd></div>
      <div><dt data-fr27-type="field-label">Format</dt><dd data-fr27-type="meta">${escapeHtml(format)}</dd></div>
      <div><dt data-fr27-type="field-label">Time precision</dt><dd data-fr27-type="meta">${escapeHtml(precision)}</dd></div>
      <div><dt data-fr27-type="field-label">Timezone</dt><dd data-fr27-type="meta">${escapeHtml(event.timezone || "Europe/Paris")}</dd></div>
    </dl></section>`;
  }

  function renderDossierParticipants(event) {
    const participants = Array.isArray(event.candidate_names) && event.candidate_names.filter(Boolean).length
      ? event.candidate_names.filter(Boolean)
      : Array.isArray(event.participants)
        ? event.participants.filter(Boolean)
        : [];
    if (participants.length <= 1) {
      const lead = participants[0] || String(event.organization || "").trim() || "No named participant is published.";
      const note = participants.length === 1
        ? "SOLO APPEARANCE"
        : event.organization
          ? "ORGANISATION-LED"
          : "NO NAMED PARTICIPANT";
      return `<section class="hybrid-events-dossier-involvement"><h4 data-fr27-type="module-title">INVOLVEMENT</h4><strong data-fr27-type="item-title">${escapeHtml(lead)}</strong><small data-fr27-type="status-label">${escapeHtml(note)}</small></section>`;
    }
    return `<section class="hybrid-events-dossier-participants"><h4 data-fr27-type="module-title">PARTICIPANTS · ${participants.length}</h4><div>${participants.map(name => `<span data-fr27-type="row-label">${escapeHtml(name)}</span>`).join("")}</div></section>`;
  }

  function renderDossierEvidence(event) {
    const evidence = campaignEventPrimaryEvidence(event);
    const evidenceState = campaignEventEvidencePresentation(event);
    if (!evidence) {
      return `<section class="hybrid-events-dossier-evidence"><h4 data-fr27-type="module-title">SOURCE EVIDENCE</h4><div class="hybrid-state is-compact" data-fr27-type="status-label">Source evidence is unavailable.</div></section>`;
    }
    return `<section class="hybrid-events-dossier-evidence"><div class="hybrid-events-dossier-section-head"><h4 data-fr27-type="module-title">SOURCE EVIDENCE</h4><span data-fr27-type="status-label">PRIMARY</span></div>
      <div class="hybrid-events-evidence-primary">
        <div><strong data-fr27-type="row-label">${escapeHtml(evidence.source_publisher || "Source")}</strong><span data-fr27-type="meta">${escapeHtml(campaignEventSourceTypeLabel(evidence.source_type))}</span></div>
        <time data-fr27-type="meta" datetime="${escapeAttribute(event.last_verified_at || "")}">${escapeHtml(campaignEventObservedLabel(event.last_verified_at))}</time>
      </div>
      <p data-fr27-type="body">${escapeHtml(campaignEventEvidenceTypeLabel(evidence.evidence_type))}</p>
      <div class="hybrid-events-evidence-actions"><span class="hybrid-events-evidence-chip" data-fr27-type="status-label" data-evidence-status="${escapeAttribute(evidenceState.key)}">${escapeHtml(evidenceState.label)}</span>${sourceLink(evidence.source_url, "OPEN SOURCE", "hybrid-events-dossier-source", `Open source for ${event.title}`)}</div>
    </section>`;
  }

  function renderDossierHistory(model) {
    const updates = model.selectedUpdates.slice(0, 8);
    if (!updates.length) {
      return `<section class="hybrid-events-history"><div class="hybrid-events-dossier-section-head"><h4 data-fr27-type="module-title">SCHEDULE HISTORY</h4><span data-fr27-type="status-label">NO RECORDS</span></div><div class="hybrid-events-history-empty-state"><strong data-fr27-type="status-label">NO PUBLISHED SCHEDULE HISTORY</strong><span data-fr27-type="meta">No calendar update is currently linked to this event.</span></div></section>`;
    }
    const hasMaterialUpdate = updates.some(update => String(update.update_type || "").toUpperCase() !== "NEW");
    const rows = updates.map(update => `<article class="hybrid-events-history-item" data-update-type="${escapeAttribute(String(update.update_type || "updated").toLowerCase())}"><i aria-hidden="true"></i><time data-fr27-type="scale-label" datetime="${escapeAttribute(update.observed_at)}">${escapeHtml(campaignEventObservedLabel(update.observed_at))}</time><span class="hybrid-events-watch-type" data-fr27-type="status-label" data-update-type="${escapeAttribute(String(update.update_type || "updated").toLowerCase())}">${escapeHtml(String(update.update_type || "UPDATED").toUpperCase())}</span><small data-fr27-type="meta">${escapeHtml(campaignEventUpdateCopy(update))}</small></article>`).join("");
    const quietState = hasMaterialUpdate
      ? ""
      : `<div class="hybrid-events-history-empty-state"><strong data-fr27-type="status-label">NO FURTHER SCHEDULE CHANGES</strong><span data-fr27-type="meta">No later confirmed, updated, postponed or cancelled schedule change is published for this event.</span></div>`;
    return `<section class="hybrid-events-history"><div class="hybrid-events-dossier-section-head"><h4 data-fr27-type="module-title">SCHEDULE HISTORY</h4><span data-fr27-type="data">${updates.length} RECORD${updates.length === 1 ? "" : "S"}</span></div><div class="hybrid-events-history-list">${rows}</div>${quietState}</section>`;
  }

  function renderEventDossier(model) {
    const event = model.selectedEvent;
    if (!event) {
      return `<section class="hybrid-events-dossier"><div class="hybrid-events-panel-head"><h3 data-fr27-type="panel-title">EVENT DOSSIER</h3><span data-fr27-type="meta">SOURCE-LINKED EVIDENCE</span></div><div class="hybrid-state" data-fr27-type="status-label">No campaign event is selected.</div></section>`;
    }
    const status = campaignEventStatusPresentation(event);
    const evidenceState = campaignEventEvidencePresentation(event);
    const participantCount = campaignEventParticipantCount(event);
    const place = campaignEventPlaceLabel(event) || "Location not published";
    const when = `${campaignEventLongDate(event.scheduled_start)}${campaignEventTimeLabel(event) !== "—" ? ` · ${campaignEventTimeLabel(event)}` : ""}`;
    const format = campaignEventTypeDisplayLabel(event.event_type);

    return `<section class="hybrid-events-dossier" aria-labelledby="hybrid-events-dossier-title">
      <div class="hybrid-events-panel-head"><h3 id="hybrid-events-dossier-title" data-fr27-type="panel-title">EVENT DOSSIER</h3><span class="hybrid-events-dossier-head-meta" data-fr27-type="meta">SOURCE-LINKED EVIDENCE <button class="hybrid-events-dossier-info fr27-info-glyph" type="button" aria-label="Event evidence methodology" data-fr27-tooltip="Past scheduled events remain scheduled until explicit occurrence evidence confirms they took place.">i</button></span></div>
      <div class="hybrid-events-dossier-body">
        <div class="hybrid-events-dossier-title">${renderEventTypeBadge(event.event_type, participantCount > 1 ? `×${participantCount}` : "")}<div><h4 lang="fr" data-fr27-type="item-title">${escapeHtml(event.title)}</h4><div><span class="hybrid-events-status" data-fr27-type="status-label" data-event-status="${escapeAttribute(status.key)}">${escapeHtml(status.label)}</span><span class="hybrid-events-evidence-chip" data-fr27-type="status-label" data-evidence-status="${escapeAttribute(evidenceState.key)}">${escapeHtml(evidenceState.label)}</span></div></div></div>
        <div class="hybrid-events-dossier-lede">
          <div><small data-fr27-type="field-label">DATE / TIME</small><strong data-fr27-type="meta">${escapeHtml(when)}</strong></div>
          <div><small data-fr27-type="field-label">VENUE</small><strong data-fr27-type="meta">${escapeHtml(place)}</strong></div>
          <div><small data-fr27-type="field-label">FORMAT</small><strong data-fr27-type="meta">${escapeHtml(format)}</strong></div>
        </div>
        <div class="hybrid-events-dossier-grid">
          <div class="hybrid-events-dossier-left">${renderDossierParticipants(event)}${renderDossierEventDetails(event)}</div>
          ${renderDossierEvidence(event)}
        </div>

      </div>
    </section>`;
  }

  function renderScheduleWatchMaterialItem(update, model) {
    const event = update.event;
    const observed = campaignEventObservedParts(update.observed_at);
    const weekStart = event ? campaignEventWeekStartKey(campaignEventDateKey(event)) : "";
    const title = event?.title || update.headline || "Campaign calendar update";
    const schedule = event ? `${campaignEventShortDate(event.scheduled_start)}${campaignEventTimeLabel(event) !== "—" ? ` · ${campaignEventTimeLabel(event)}` : ""}` : "Schedule unavailable";
    const selected = model.selectedEvent?.event_id === update.event_id;
    return `<button type="button" class="hybrid-events-watch-material-item${selected ? " is-selected" : ""}" data-hybrid-event-id="${escapeAttribute(update.event_id)}" ${weekStart ? `data-hybrid-event-week="${escapeAttribute(weekStart)}"` : ""}>
      <span class="hybrid-events-watch-type" data-fr27-type="status-label" data-update-type="${escapeAttribute(String(update.update_type || "updated").toLowerCase())}">${escapeHtml(String(update.update_type || "UPDATED").toUpperCase())}</span>
      <span class="hybrid-events-watch-material-copy"><strong lang="fr" data-fr27-type="item-title">${escapeHtml(title)}</strong><small data-fr27-type="meta">${escapeHtml(schedule)} · ${escapeHtml(campaignEventUpdateCopy(update))}</small></span>
      <time data-fr27-type="scale-label" datetime="${escapeAttribute(update.observed_at)}"><strong>${escapeHtml(observed.time || "—")}</strong><span>${escapeHtml(observed.date)}</span></time>
    </button>`;
  }

  function renderScheduleWatchAddition(update, model) {
    const event = update.event;
    const evidence = campaignEventPrimaryEvidence(update);
    const publisher = String(evidence?.source_publisher || "Source").trim();
    const weekStart = event ? campaignEventWeekStartKey(campaignEventDateKey(event)) : "";
    const title = event?.title || update.headline || "Campaign calendar addition";
    const schedule = event ? `${campaignEventShortDate(event.scheduled_start)}${campaignEventTimeLabel(event) !== "—" ? ` · ${campaignEventTimeLabel(event)}` : ""}` : "Schedule unavailable";
    const selected = model.selectedEvent?.event_id === update.event_id;
    return `<button type="button" class="hybrid-events-watch-addition${selected ? " is-selected" : ""}" data-event-type="${escapeAttribute(event?.event_type || "other")}" data-hybrid-event-id="${escapeAttribute(update.event_id)}" ${weekStart ? `data-hybrid-event-week="${escapeAttribute(weekStart)}"` : ""}>
      <i class="hybrid-events-watch-event-node" aria-hidden="true"></i>
      <strong lang="fr" data-fr27-type="item-title">${escapeHtml(title)}</strong><small data-fr27-type="meta">${escapeHtml(schedule)} · ${escapeHtml(publisher)}</small>
    </button>`;
  }

  function renderScheduleWatch(model) {
    const materialUpdates = model.eventWatch.filter(update => String(update.update_type || "").toUpperCase() !== "NEW");
    const additionGroups = groupCampaignEventAdditions(model.eventWatch);
    const materialContent = materialUpdates.length
      ? materialUpdates.map(update => renderScheduleWatchMaterialItem(update, model)).join("")
      : `<div class="hybrid-events-watch-empty"><i aria-hidden="true">✓</i><strong data-fr27-type="status-label">MATERIAL CHANGES 0</strong></div>`;
    const additions = additionGroups.length
      ? additionGroups.map(group => {
          const observed = campaignEventObservedParts(group.observedAt);
          return `<section class="hybrid-events-watch-addition-group"><i class="hybrid-events-watch-group-node" aria-hidden="true"></i><div class="hybrid-events-watch-addition-head"><span data-fr27-type="scale-label">${escapeHtml(observed.date)}${observed.time ? ` · ${escapeHtml(observed.time)}` : ""}</span><strong data-fr27-type="status-label">+${group.updates.length} NEW</strong></div><div>${group.updates.map(update => renderScheduleWatchAddition(update, model)).join("")}</div></section>`;
        }).join("")
      : '<div class="hybrid-events-watch-empty"><strong data-fr27-type="status-label">NO RECENT ADDITIONS</strong><span data-fr27-type="meta">No newly published event is recorded in the current watch log.</span></div>';

    return `<section class="hybrid-events-schedule-watch" aria-labelledby="hybrid-events-schedule-watch-title">
      <div class="hybrid-events-panel-head"><div><h3 id="hybrid-events-schedule-watch-title" data-fr27-type="panel-title">SCHEDULE WATCH</h3><span data-fr27-type="meta">CALENDAR ACTIVITY</span></div><span data-fr27-type="data">${model.watchCount} RECORDS</span></div>
      <div class="hybrid-events-schedule-watch-body">
        <section class="hybrid-events-watch-section is-material">${materialContent}</section>
        <section class="hybrid-events-watch-section is-additions"><div class="hybrid-events-watch-section-head"><h4 data-fr27-type="module-title">RECENT ADDITIONS</h4><span data-fr27-type="data">${model.eventWatch.length - materialUpdates.length}</span></div><div class="hybrid-events-watch-timeline">${additions}</div></section>
      </div>
    </section>`;
  }

  function renderEventsPanel(model) {
    if (model.state !== "ready") {
      if (model.state === "loading" && window.FR27UI) {
        return window.FR27UI.skeletonElement(
          "events",
          "Loading campaign events"
        ).outerHTML;
      }
      return summaryState(model);
    }
    return `<div class="hybrid-events-workspace" aria-label="Campaign Events temporal operations desk">
      ${renderOperationsScheduleRail(model)}
      <div class="hybrid-events-ops-main">
        ${renderUpcomingPanel(model)}
        ${renderEventDossier(model)}
        ${renderScheduleWatch(model)}
      </div>
      ${renderOperationsHorizonLegend(model)}
    </div>`;
  }

  function renderFocusWorkspace(models) {
    return `<section class="hybrid-workspace" data-hybrid-workspace aria-label="Signal Board focus workspace">
      <div class="hybrid-tabs" role="tablist" aria-label="Lower evidence workspace" aria-orientation="horizontal">
        ${viewOrder.map(key => `<button class="hybrid-tab" id="${views[key].tabId}" type="button" role="tab" data-fr27-type="nav-label"
          data-hybrid-view="${key}" aria-controls="${views[key].panelId}" aria-selected="${String(state.activeView === key)}" tabindex="${state.activeView === key ? "0" : "-1"}">
          ${workspaceTabIconMarkup(key)}
          <span class="hybrid-tab-label">${views[key].label}</span>
        </button>`).join("")}
      </div>
      <section class="hybrid-panel" id="signal-runoff-panel" role="tabpanel" aria-labelledby="signal-runoff-tab"${state.activeView === "runoff" ? "" : " hidden"}>${renderRunoffPanel(models.runoff)}</section>
      <section class="hybrid-panel" id="signal-candidates-panel" role="tabpanel" aria-labelledby="signal-candidates-tab"${state.activeView === "candidates" ? "" : " hidden"}>
        <div id="candidate-signals-root" data-candidate-signals-state="${state.candidateSignals.status}">
          ${window.FR27UI ? window.FR27UI.skeletonElement("candidates", "Loading candidate evidence").outerHTML : '<div class="candidate-signals-state" role="status" aria-label="Loading candidate evidence">—</div>'}
        </div>
      </section>
      <section class="hybrid-panel" id="signal-events-panel" role="tabpanel" aria-labelledby="signal-events-tab"${state.activeView === "events" ? "" : " hidden"}>${renderEventsPanel(models.events)}</section>
      <section class="hybrid-panel" id="signal-agenda-panel" role="tabpanel" aria-labelledby="signal-agenda-tab"${state.activeView === "agenda" ? "" : " hidden"}>${renderAgendaPanel(models.agenda)}</section>
      <section class="hybrid-panel" id="signal-issues-panel" role="tabpanel" aria-labelledby="signal-issues-tab"${state.activeView === "issues" ? "" : " hidden"}>${renderIssuesPanel(models.issues)}</section>
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


  function candidateScrutinyCompareText(left, right) {
    const a = String(left || "");
    const b = String(right || "");
    if (a === b) return 0;
    return a < b ? -1 : 1;
  }

  function candidateScrutinyReviewEntries(candidate, claimsPayload) {
    if (
      !candidate ||
      !Array.isArray(claimsPayload?.reviews)
    ) {
      return [];
    }

    return claimsPayload.reviews
      .map(review => {
        const association =
          Array.isArray(review?.candidate_associations)
            ? review.candidate_associations.find(
              item =>
                item?.candidate_id ===
                candidate.candidate_id
            )
            : null;

        return association
          ? {
            review,
            relationship:
              association.relationship
          }
          : null;
      })
      .filter(Boolean)
      .sort((left, right) =>
        candidateScrutinyCompareText(
          right.review?.review_date,
          left.review?.review_date
        ) ||
        candidateScrutinyCompareText(
          left.review?.publisher_name,
          right.review?.publisher_name
        ) ||
        candidateScrutinyCompareText(
          left.review?.id,
          right.review?.id
        )
      );
  }

  function candidateScrutinyDetailState(candidate) {
    const loadState =
      dashboardState.loadState?.claims;

    if (loadState === "loading") {
      return {
        state: "loading",
        reviews: []
      };
    }

    if (loadState === "error") {
      return {
        state: "unavailable",
        reviews: []
      };
    }

    const claimsPayload =
      dashboardState.claims;

    if (
      !claimsPayload ||
      !Array.isArray(claimsPayload.reviews)
    ) {
      return {
        state: "unavailable",
        reviews: []
      };
    }

    return {
      state: "ready",
      reviews:
        candidateScrutinyReviewEntries(
          candidate,
          claimsPayload
        )
    };
  }

  function candidateScrutinyNode(
    tagName,
    className = "",
    text = null
  ) {
    const node =
      document.createElement(tagName);

    if (className) {
      node.className = className;
    }

    if (text !== null) {
      node.textContent = text;
    }

    return node;
  }

  function candidateScrutinyReviewRow(entry) {
    const review = entry.review;
    const relationship =
      String(entry.relationship || "")
        .toLowerCase();

    const row = candidateScrutinyNode(
      "article",
      "candidate-signals-scrutiny-review"
    );

    const meta = candidateScrutinyNode(
      "div",
      "candidate-signals-scrutiny-review-meta"
    );

    const relationshipNode =
      candidateScrutinyNode(
        "span",
        `candidate-signals-scrutiny-relationship is-${relationship}`,
        relationship.toUpperCase()
      );

    const dateNode =
      candidateScrutinyNode(
        "time",
        "candidate-signals-scrutiny-review-date",
        review.review_date
          ? formatDay(review.review_date)
          : "DATE UNAVAILABLE"
      );

    if (review.review_date) {
      dateNode.setAttribute(
        "datetime",
        review.review_date
      );
    }

    meta.append(
      relationshipNode,
      dateNode,
      candidateScrutinyNode(
        "span",
        "candidate-signals-scrutiny-publisher",
        String(review.publisher_name || "")
      )
    );

    const claim = candidateScrutinyNode(
      "p",
      "candidate-signals-scrutiny-claim"
    );

    const claimText = String(
      review.claim_text || ""
    );

    const terminalPunctuation =
      /^(.*?)(\S+\s+[?!;:])$/s.exec(
        claimText
      );

    if (terminalPunctuation) {
      claim.append(
        document.createTextNode(
          terminalPunctuation[1]
        ),
        candidateScrutinyNode(
          "span",
          "candidate-signals-scrutiny-no-break-tail",
          terminalPunctuation[2]
        )
      );
    } else {
      claim.textContent = claimText;
    }

    const footer = candidateScrutinyNode(
      "div",
      "candidate-signals-scrutiny-review-footer"
    );

    footer.append(
      candidateScrutinyNode(
        "span",
        "candidate-signals-scrutiny-rating",
        String(review.rating || "")
      )
    );

    const sourceUrl =
      safeSourceUrl(review.review_url);

    if (sourceUrl) {
      const link = candidateScrutinyNode(
        "a",
        "candidate-signals-scrutiny-source",
        "OPEN SOURCE ↗"
      );

      link.href = sourceUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.setAttribute(
        "aria-label",
        `Open ${review.publisher_name || "publisher"} review source in a new tab`
      );

      footer.append(link);
    } else {
      footer.append(
        candidateScrutinyNode(
          "span",
          "candidate-signals-scrutiny-source is-unavailable",
          "SOURCE UNAVAILABLE"
        )
      );
    }

    row.append(meta, claim, footer);
    return row;
  }

  function candidateScrutinyBody(detailState) {
    const body = candidateScrutinyNode(
      "div",
      "candidate-signals-scrutiny-body"
    );

    if (detailState.state === "loading") {
      body.append(
        window.FR27UI
          ? window.FR27UI.skeletonElement(
              "list",
              "Loading monitored publisher reviews"
            )
          : candidateScrutinyNode(
              "div",
              "candidate-signals-scrutiny-state",
              "—"
            )
      );
      return body;
    }

    if (detailState.state !== "ready") {
      const state = candidateScrutinyNode(
        "div",
        "candidate-signals-scrutiny-state"
      );
      state.append(
        candidateScrutinyNode(
          "strong",
          "candidate-signals-scrutiny-state-title",
          "DETAIL UNAVAILABLE"
        ),
        candidateScrutinyNode(
          "p",
          "",
          "Candidate scrutiny summary remains available."
        ),
        candidateScrutinyNode(
          "p",
          "",
          "Detailed publisher reviews could not be loaded."
        )
      );
      body.append(state);
      return body;
    }

    if (!detailState.reviews.length) {
      const state = candidateScrutinyNode(
        "div",
        "candidate-signals-scrutiny-state"
      );
      state.append(
        candidateScrutinyNode(
          "strong",
          "candidate-signals-scrutiny-state-title",
          "NO PUBLISHED REVIEWS"
        ),
        candidateScrutinyNode(
          "p",
          "",
          "No monitored publisher review is currently associated with this candidate."
        )
      );
      body.append(state);
      return body;
    }

    const list = candidateScrutinyNode(
      "div",
      "candidate-signals-scrutiny-review-list"
    );

    detailState.reviews.forEach(
      entry => {
        list.append(
          candidateScrutinyReviewRow(entry)
        );
      }
    );

    const disclosure = candidateScrutinyNode(
      "p",
      "candidate-signals-scrutiny-disclosure",
      "BY — candidate is the recorded claimant. ABOUT — candidate is mentioned in a checked claim attributed to somebody else."
    );

    body.append(list, disclosure);
    return body;
  }

  function closeCandidateScrutinyPopover(
    options = {}
  ) {
    if (!candidateScrutinyPopover) {
      return;
    }

    const active =
      candidateScrutinyPopover;

    candidateScrutinyPopover = null;

    document.removeEventListener(
      "pointerdown",
      active.onOutsidePointerDown,
      true
    );

    document.removeEventListener(
      "keydown",
      active.onKeyDown,
      true
    );

    window.removeEventListener(
      "resize",
      active.onViewportChange
    );

    window.removeEventListener(
      "scroll",
      active.onViewportChange,
      true
    );

    active.anchor?.setAttribute(
      "aria-expanded",
      "false"
    );

    active.anchor?.removeAttribute(
      "aria-controls"
    );

    active.panel?.remove();

    if (
      options.restoreFocus !== false &&
      active.anchor &&
      active.anchor.isConnected !== false &&
      typeof active.anchor.focus ===
        "function"
    ) {
      active.anchor.focus();
    }
  }

  function positionCandidateScrutinyPopover() {
    const active =
      candidateScrutinyPopover;

    if (!active) return;

    const {
      panel,
      anchor
    } = active;

    if (
      anchor.isConnected === false
    ) {
      closeCandidateScrutinyPopover({
        restoreFocus: false
      });
      return;
    }

    const compact =
      typeof window.matchMedia ===
        "function"
        ? window.matchMedia(
          "(max-width: 640px)"
        ).matches
        : window.innerWidth <= 640;

    panel.classList.toggle(
      "is-sheet",
      compact
    );

    panel.style.removeProperty("left");
    panel.style.removeProperty("top");
    panel.style.removeProperty("width");

    if (compact) return;

    const margin = 12;
    const gap = 8;
    const width = Math.min(
      440,
      Math.max(
        400,
        window.innerWidth -
          margin * 2
      )
    );

    panel.style.width =
      `${width}px`;

    const anchorRect =
      anchor.getBoundingClientRect();

    const panelRect =
      panel.getBoundingClientRect();

    let left =
      anchorRect.right - width;

    left = Math.max(
      margin,
      Math.min(
        left,
        window.innerWidth -
          width -
          margin
      )
    );

    let top =
      anchorRect.bottom + gap;

    const roomBelow =
      window.innerHeight -
      anchorRect.bottom -
      margin -
      gap;

    const roomAbove =
      anchorRect.top -
      margin -
      gap;

    if (
      panelRect.height > roomBelow &&
      roomAbove > roomBelow
    ) {
      top =
        anchorRect.top -
        panelRect.height -
        gap;
    }

    top = Math.max(
      margin,
      Math.min(
        top,
        window.innerHeight -
          panelRect.height -
          margin
      )
    );

    panel.style.left =
      `${Math.round(left)}px`;

    panel.style.top =
      `${Math.round(top)}px`;
  }

  function openCandidateScrutinyPopover(
    candidate,
    anchorElement
  ) {
    if (
      !candidate ||
      !anchorElement ||
      !document.body
    ) {
      return null;
    }

    closeCandidateScrutinyPopover({
      restoreFocus: false
    });

    const detailState =
      candidateScrutinyDetailState(
        candidate
      );

    const panel =
      candidateScrutinyNode(
        "section",
        "candidate-signals-scrutiny-popover"
      );

    panel.dataset.candidateScrutinyPopover =
      "true";

    panel.setAttribute(
      "role",
      "dialog"
    );

    panel.setAttribute(
      "aria-modal",
      "false"
    );

    const safeCandidateId =
      String(
        candidate.candidate_id || "candidate"
      ).replace(/[^a-z0-9_-]+/gi, "-");

    panel.id =
      `candidate-signals-scrutiny-popover-${safeCandidateId}`;

    const titleId =
      `${panel.id}-title`;

    const countId =
      `${panel.id}-count`;

    panel.setAttribute(
      "aria-labelledby",
      titleId
    );

    panel.setAttribute(
      "aria-describedby",
      countId
    );

    const header =
      candidateScrutinyNode(
        "header",
        "candidate-signals-scrutiny-header"
      );

    const heading =
      candidateScrutinyNode(
        "div",
        "candidate-signals-scrutiny-heading"
      );

    const title =
      candidateScrutinyNode(
        "h2",
        "candidate-signals-scrutiny-title",
        `CLAIM SCRUTINY · ${candidate.candidate_name}`
      );

    title.id = titleId;

    const summaryCount =
      Number(
        candidate.scrutiny?.archive
          ?.review_count
      );

    const reviewCount =
      detailState.state === "ready"
        ? detailState.reviews.length
        : Number.isFinite(summaryCount)
          ? summaryCount
          : 0;

    const count =
      candidateScrutinyNode(
        "p",
        "candidate-signals-scrutiny-count",
        `${reviewCount} MONITORED PUBLISHER ${
          reviewCount === 1
            ? "REVIEW"
            : "REVIEWS"
        }`
      );

    count.id = countId;

    heading.append(title, count);

    const close =
      candidateScrutinyNode(
        "button",
        "candidate-signals-scrutiny-close",
        "×"
      );

    close.type = "button";
    close.setAttribute(
      "aria-label",
      `Close claim scrutiny for ${candidate.candidate_name}`
    );

    header.append(heading, close);

    panel.append(
      header,
      candidateScrutinyBody(
        detailState
      )
    );

    document.body.append(panel);

    anchorElement.setAttribute(
      "aria-expanded",
      "true"
    );

    anchorElement.setAttribute(
      "aria-controls",
      panel.id
    );

    const onOutsidePointerDown =
      event => {
        if (
          panel.contains(event.target) ||
          anchorElement.contains(
            event.target
          )
        ) {
          return;
        }

        closeCandidateScrutinyPopover();
      };

    const onKeyDown =
      event => {
        if (event.key !== "Escape") {
          return;
        }

        event.preventDefault();
        closeCandidateScrutinyPopover();
      };

    const onViewportChange =
      () => {
        positionCandidateScrutinyPopover();
      };

    candidateScrutinyPopover = {
      panel,
      anchor: anchorElement,
      onOutsidePointerDown,
      onKeyDown,
      onViewportChange
    };

    close.addEventListener(
      "click",
      () => {
        closeCandidateScrutinyPopover();
      }
    );

    document.addEventListener(
      "pointerdown",
      onOutsidePointerDown,
      true
    );

    document.addEventListener(
      "keydown",
      onKeyDown,
      true
    );

    window.addEventListener(
      "resize",
      onViewportChange
    );

    window.addEventListener(
      "scroll",
      onViewportChange,
      true
    );

    positionCandidateScrutinyPopover();
    close.focus();

    return panel;
  }

  function renderCandidateSignalsPanel() {
    closeCandidateScrutinyPopover({
      restoreFocus: false
    });

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
        onOpenScrutiny(
          candidate,
          anchorElement
        ) {
          openCandidateScrutinyPopover(
            candidate,
            anchorElement
          );
        },
        candidateAttention:
          state.candidateAttention,
        candidateVisibilityHistory:
          state.candidateVisibilityHistory,
        candidateAgendaHistory:
          state.candidateAgendaHistory,
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

    if (view !== "candidates") {
      closeCandidateScrutinyPopover({
        restoreFocus: false
      });
    }

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
    state.scrollOnNextHash = source === "card";
    if (window.location.hash === views[view].hash) {
      setActiveSignalView(view, { scrollWorkspace: state.scrollOnNextHash });
      state.scrollOnNextHash = false;
      return;
    }
    window.location.hash = views[view].hash;
  }

  function scrollWorkspaceIfNeeded() {
    const target = mount.querySelector(
      "[data-hybrid-workspace]"
    );
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

    mount
      .querySelectorAll(
        "[data-hybrid-policy-issue]"
      )
      .forEach(button => {
        button.addEventListener(
          "click",
          () => {
            state.selectedPolicyIssueId =
              button.dataset
                .hybridPolicyIssue;

            renderAll();

            mount
              .querySelector(
                `[data-hybrid-policy-issue="${CSS.escape(state.selectedPolicyIssueId)}"]`
              )
              ?.focus();
          }
        );
      });

    mount.querySelectorAll("button[data-hybrid-event-id]").forEach(button => {
      button.addEventListener("click", () => {
        state.selectedCampaignEventId = button.dataset.hybridEventId;
        if (button.dataset.hybridEventWeek) {
          state.selectedCampaignEventWeekStart = button.dataset.hybridEventWeek;
        }
        renderAll();
        mount.querySelector(`button[data-hybrid-event-id="${CSS.escape(state.selectedCampaignEventId)}"]`)?.focus();
      });
    });

    mount.querySelectorAll("button[data-hybrid-events-filter]").forEach(button => {
      button.addEventListener("click", () => {
        state.campaignEventTypeFilter = button.dataset.hybridEventsFilter || "all";
        state.selectedCampaignEventId = "";
        state.selectedCampaignEventWeekStart = "";
        renderAll();
        mount.querySelector(`button[data-hybrid-events-filter="${CSS.escape(state.campaignEventTypeFilter)}"]`)?.focus();
      });
    });

    mount.querySelectorAll("button[data-hybrid-week-select]").forEach(button => {
      button.addEventListener("click", () => {
        state.selectedCampaignEventWeekStart = button.dataset.hybridWeekSelect;
        renderAll();
        const target = mount.querySelector(`[data-hybrid-event-week-group="${CSS.escape(state.selectedCampaignEventWeekStart)}"]`);
        target?.scrollIntoView({ block: "nearest", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        mount.querySelector(`button[data-hybrid-week-select="${CSS.escape(state.selectedCampaignEventWeekStart)}"]`)?.focus();
      });
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
        ? "Comparable change in active-field mention rate, in percentage points."
        : model.candidateCoverageAvailable
          ? `Raw arithmetic current-minus-prior mention-rate differences are displayed because comparison quality is not comparable; reason: ${reason || "unknown"}. These values are descriptive and are not comparable trend estimates.`
          : "Active-field mention-rate comparison unavailable."
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
      if (model.state === "loading" && window.FR27UI) {
        return window.FR27UI.skeletonElement(
          "media",
          "Loading Media Pulse"
        ).outerHTML;
      }
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
          <span class="top-media-coverage-meta" data-fr27-type="meta">
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
              data-fr27-type="item-title"
              lang="fr"
            >${escapeHtml(item.headline)}</span>

            <span class="top-media-source-link" data-fr27-type="action-label">
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
            const latestShareRole = latestShareText === "—" ? "meta" : "data";
            const previousShareRole = previousShareText === "—" ? "meta" : "data";
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
                    ? `${item.name}, ${item.tierLabel}: ${latestShareText} percent mention rate among active-field-linked race records in the current period, ${previousShareText} percent in the prior period, comparable change ${deltaText}`
                    : rawDeltaAvailable
                      ? `${item.name}, ${item.tierLabel}: ${latestShareText} percent mention rate among active-field-linked race records in the current period, ${previousShareText} percent in the prior period, raw arithmetic difference ${deltaText}. Publisher panels changed, so this is not a comparable trend estimate.`
                      : `${item.name}, ${item.tierLabel}: ${latestShareText} percent mention rate among active-field-linked race records in the current period, ${previousShareText} percent in the prior period.`
                )}"
              >
                <span class="top-media-shift-name" data-fr27-type="row-label">
                  ${escapeHtml(item.name)}
                  <small class="hybrid-status-chip" data-fr27-type="status-label">${escapeHtml(item.tierLabel)}</small>
                </span>
                <strong data-fr27-type="${latestShareRole}">${latestShareText}${latestShareText === "—" ? "" : "%"}</strong>
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
                <em class="top-media-shift-prior-value" data-fr27-type="${previousShareRole}">
                  ${previousShareText}${previousShareText === "—" ? "" : "%"}
                </em>
                <b class="${directionClass}" data-fr27-type="${displayedDelta === null ? "meta" : "data"}" aria-hidden="true">
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
            <span data-fr27-type="row-label">
              ${escapeHtml(topic.label)}
            </span>

            <i aria-hidden="true">
              <b
                style="--top-topic-width:${topicWidth.toFixed(2)}%"
              ></b>
            </i>

            <strong data-fr27-type="${sourceDays ? "data" : "meta"}">${sourceDays || "—"}</strong>
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

              <strong data-fr27-type="row-label">
                ${escapeHtml(publisher.name)}
              </strong>

              <b data-fr27-type="data">${publisher.count}</b>
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
            data-fr27-type="nav-label"
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
            data-fr27-type="nav-label"
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
            <h3 data-fr27-type="module-title">Latest election coverage</h3>

            <span data-fr27-type="meta">
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
            data-fr27-type="action-label"
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
              aria-label="${escapeAttribute(`Active-field mention rate. Percentage of active-field-linked race records that mention each candidate. One record may mention multiple candidates, so rates can overlap and need not total 100 percent. ${candidateComparisonExplanation}`)}"
            >
              <h3 data-fr27-type="module-title">Active-field mention rate</h3>

              <span
                class="top-media-shift-quality"
                data-fr27-tooltip="${escapeAttribute(candidateComparisonExplanation)}"
                data-fr27-tooltip-affordance="term"
                tabindex="0"
                aria-label="${escapeAttribute(candidateComparisonExplanation)}"
              >
                ${escapeHtml(candidateComparisonLabel)}
              </span>
            </div>


            <div
              class="top-media-period-legend"
              aria-label="${escapeAttribute(
                `Candidate mention rate among active-field-linked race records. One record may mention multiple candidates, so rates can overlap and need not total 100 percent. Current period ${currentPeriodLabel}; prior period ${priorPeriodLabel}.`
              )}"
            >
              <span class="is-current">
                <i aria-hidden="true"></i>
                <strong data-fr27-type="field-label">CURRENT</strong>
                <small data-fr27-type="scale-label">
                  ${escapeHtml(
                    currentPeriodLabel
                  )}
                </small>
              </span>

              <span class="is-prior">
                <i aria-hidden="true"></i>
                <strong data-fr27-type="field-label">PRIOR</strong>
                <small data-fr27-type="scale-label">
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
                <h3 data-fr27-type="module-title">Topic coverage</h3>
              </div>

              <div class="top-media-topic-list">
                ${topicRows}
              </div>

            </section>

            <section>
              <div class="top-media-section-heading">
                <h3 data-fr27-type="module-title">Top publishers</h3>
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
            data-fr27-type="action-label"
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
                <strong data-fr27-type="key-data">
                  ${escapeHtml(
                    String(metric.value)
                  )}
                </strong>
                <small data-fr27-type="field-label">
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
        topMediaMetrics.removeAttribute("aria-busy");
      } else if (model.state === "loading" && window.FR27UI) {
        topMediaMetrics.replaceChildren(
          window.FR27UI.skeletonElement(
            "metrics",
            "Loading media metrics"
          )
        );
        topMediaMetrics.setAttribute("aria-busy", "true");
      } else {
        topMediaMetrics.textContent =
          model.message ||
          "Media data unavailable";
        topMediaMetrics.removeAttribute("aria-busy");
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
    buildEventsViewModel,
    agendaMovementLabel,
    agendaStructureLabel,
    buildAgendaViewModel,
    buildPolicyAgendaViewModel,
    renderSummaryGrid,
    renderRunoffSummary,
    renderMediaSummary,
    renderAgendaSummary,
    renderFocusWorkspace,
    renderRunoffPanel,
    renderMediaPanel,
    renderEventsPanel,
    renderAgendaPanel,
    renderIssuesPanel,
    setActiveSignalView,
    handleSignalHashChange
  });
})();
