(() => {
  "use strict";

  const mount = document.getElementById("hybrid-signal-board");
  if (!mount) return;

  const views = Object.freeze({
    runoff: { label: "RUNOFF", title: "Closest Runoff", hash: "#signal-runoff", index: "1" },
    media: { label: "MEDIA PULSE", title: "Media Pulse", hash: "#signal-media", index: "2" },
    agenda: { label: "AGENDA", title: "Campaign Agenda", hash: "#signal-agenda", index: "3" },
    claims: { label: "CLAIM SCRUTINY", title: "Claim Scrutiny", hash: "#signal-claims", index: "4" }
  });
  const viewOrder = Object.keys(views);
  const hashToView = new Map(viewOrder.map(key => [views[key].hash, key]));
  const state = {
    activeView: hashToView.get(window.location.hash) || "media",
    selectedAgendaTopicId: "",
    claimsRelationship: "all",
    claimsCandidateId: "",
    claimsPublisher: "",
    scrollOnNextHash: false
  };

  const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const percent = value => Number.isFinite(value) ? formatScore(value) : "—";
  const countLabel = (value, singular, plural = singular + "s") => `${value} ${value === 1 ? singular : plural}`;
  const formatDay = value => formatDate(String(value).slice(0, 10));
  const statusCopy = status => ({
    agree: "Same closest matchup",
    split: "Pollsters split",
    ambiguous: "No single closest matchup",
    insufficient: "Insufficient comparable evidence",
    unavailable: "Unavailable"
  })[status] || "Unavailable";

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

  function buildRunoffViewModel() {
    const unavailable = viewModelState("runoff");
    if (unavailable) return { domain: "runoff", ...unavailable };

    const payload = dashboardState.runoff;
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
      commonMatchups: Array.isArray(payload.common_matchups) ? payload.common_matchups : [],
      pollsters: Array.isArray(payload.pollsters) ? payload.pollsters : []
    };

    if (payload.status !== "agree" || !payload.selected_matchup) return model;

    const selected = payload.selected_matchup;
    const observations = selected.results.map((result, sourceIndex) => ({
      ...result,
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

  function buildMediaViewModel() {
    const unavailable = viewModelState("news");
    if (unavailable) return { domain: "media", ...unavailable };

    const payload = dashboardState.news;
    const electionItems = Array.isArray(payload.election_news) ? payload.election_news : [];
    const coverageItems = Array.isArray(payload.candidate_watch) ? payload.candidate_watch : [];
    const generatedKey = String(payload.generated_at || "").slice(0, 10);
    const anchor = /^\d{4}-\d{2}-\d{2}$/.test(generatedKey)
      ? new Date(`${generatedKey}T00:00:00Z`)
      : new Date(Math.max(...electionItems.map(item => new Date(item.published_at).getTime())));
    const safeAnchor = Number.isFinite(anchor.getTime()) ? anchor : new Date();
    const activityCounts = new Map();

    electionItems.forEach(item => {
      const key = String(item.published_at).slice(0, 10);
      activityCounts.set(key, (activityCounts.get(key) || 0) + 1);
    });

    const dailyActivity = [];
    for (let offset = 13; offset >= 0; offset -= 1) {
      const date = new Date(safeAnchor);
      date.setUTCDate(date.getUTCDate() - offset);
      const key = utcDateKey(date);
      dailyActivity.push({ key, date, count: activityCounts.get(key) || 0 });
    }

    const publisherCounts = new Map();
    electionItems.forEach(item => publisherCounts.set(item.publisher, (publisherCounts.get(item.publisher) || 0) + 1));
    const publisherContribution = [...publisherCounts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "fr"))
      .slice(0, 5);

    const candidateArticles = new Map();
    coverageItems.forEach((item, itemIndex) => {
      const articleKey = String(item.id || safeSourceUrl(item.url) || itemIndex);
      new Set(item.candidates).forEach(candidate => {
        if (!candidateArticles.has(candidate)) candidateArticles.set(candidate, new Set());
        candidateArticles.get(candidate).add(articleKey);
      });
    });
    const candidateCoverage = [...candidateArticles.entries()]
      .map(([name, items]) => ({ name, count: items.size }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "fr"));

    const headlines = newestNewsItems(electionItems).slice(0, 5);
    const windowDays = number(payload.window_days);
    const activityWindowDays = dailyActivity.length;
    const activityItemCount = dailyActivity.reduce((sum, day) => sum + day.count, 0);
    return {
      domain: "media",
      state: electionItems.length ? "ready" : "empty",
      windowDays,
      activityWindowDays,
      activityItemCount,
      electionNewsCount: number(payload.counts?.election_news),
      candidateWatchCount: coverageItems.length,
      healthyFeedCount: Array.isArray(payload.sources)
        ? payload.sources.filter(source => source.status === "ok").length
        : number(payload.counts?.successful_sources),
      configuredPublisherCount: Array.isArray(payload.sources) ? payload.sources.length : 0,
      dailyActivity,
      activityMax: Math.max(1, ...dailyActivity.map(day => day.count)),
      publisherContribution,
      publisherMax: Math.max(1, ...publisherContribution.map(item => item.count)),
      candidateCoverage,
      candidateMax: Math.max(1, ...candidateCoverage.map(item => item.count)),
      headlines,
      latestAcceptedAt: headlines[0]?.published_at || "",
      generatedAt: payload.generated_at
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
      method: agenda?.method || ""
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
    const config = views[view];
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

  function renderMediaSummary(model) {
    if (model.state !== "ready") return cardShell("media", "Latest 14 calendar days", summaryState(model));
    return cardShell("media", `14-day activity · ${model.windowDays}-day source scope`, `
      <span class="hybrid-mini-bars" role="img" aria-label="Accepted election-news items by day for the latest 14 calendar days">
        ${activityBars(model.dailyActivity, model.activityMax, true)}
      </span>
      <span class="visually-hidden">${model.dailyActivity.map(day => `${formatDay(day.key)}: ${day.count}`).join("; ")}</span>
      <span class="hybrid-media-stats">
        <span class="hybrid-mini-stat"><strong>${model.activityItemCount}</strong>${model.activityWindowDays}-day activity</span>
        <span class="hybrid-mini-stat"><strong>${model.electionNewsCount}</strong>${model.windowDays}-day news</span>
        <span class="hybrid-mini-stat"><strong>${model.candidateWatchCount}</strong>${model.windowDays}-day watch</span>
        <span class="hybrid-mini-stat"><strong>${model.healthyFeedCount}/${model.configuredPublisherCount}</strong>feeds ready</span>
      </span>
      <span class="hybrid-summary-meta">Election-news and candidate-watch totals are separate datasets. Latest accepted item: <strong>${model.latestAcceptedAt ? escapeHtml(formatNewsDateTime(model.latestAcceptedAt)) : "Unavailable"}</strong></span>`,
      `${model.activityItemCount} accepted election-news items in the displayed ${model.activityWindowDays}-day activity window; ${model.electionNewsCount} accepted election-news items and ${model.candidateWatchCount} candidate-watch records in the ${model.windowDays}-day source window; ${model.healthyFeedCount} of ${model.configuredPublisherCount} publisher feeds ready.`);
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

  function observationMarkup(observation, candidates, featured = false) {
    const [leftName, rightName] = candidates;
    const left = observation.candidates.find(item => item.name === leftName)?.score;
    const right = observation.candidates.find(item => item.name === rightName)?.score;
    return `<article class="hybrid-observation${featured ? " is-featured" : ""}">
      <div class="hybrid-observation-head"><strong>${escapeHtml(observation.pollster)}</strong><span>${featured ? "Smallest reported margin" : "Separate observation"}</span></div>
      <div class="hybrid-observation-scores">
        <span class="hybrid-observation-score">${percent(left)}</span>
        <span class="hybrid-observation-vs">VS</span>
        <span class="hybrid-observation-score is-right">${percent(right)}</span>
      </div>
      <div class="hybrid-observation-names"><span>${escapeHtml(leftName)}</span><span>${escapeHtml(rightName)}</span></div>
      <div class="hybrid-observation-foot"><strong>Reported margin ${number(observation.margin)} pts</strong>${sourceLink(observation.source_url, "Open source", "", `Open ${observation.pollster} source for ${leftName} versus ${rightName}`)}</div>
    </article>`;
  }

  function renderRunoffPanel(model) {
    if (model.state !== "ready" || !model.selectedMatchup) {
      const unresolved = ["split", "ambiguous"].includes(model.status);
      if (!unresolved) return summaryState(model);
      return `<div class="hybrid-runoff-focus-head"><div><div class="hybrid-section-title">Second-round tests</div><h3>${escapeHtml(model.statusLabel)}</h3></div><span class="hybrid-status-chip">${escapeHtml(model.fieldworkLabel)}</span></div>
        <p class="hybrid-section-sub">${escapeHtml(model.message)}</p>
        <div class="hybrid-common-grid">${model.pollsters.map(pollster => `<article class="hybrid-common-card"><h4>${escapeHtml(pollster.pollster)}</h4>${pollster.closest_matchups.map(matchup => observationMarkup(matchup.result, matchup.candidates)).join("")}</article>`).join("")}</div>
        <p class="hybrid-disclosure">Each source-reported result remains separate. No average, combined margin, probability or forecast is calculated.</p>`;
    }

    const matchup = model.selectedMatchup;
    const otherCommonMatchups = model.commonMatchups.filter(common => common.matchup_key !== matchup.key);
    return `<div class="hybrid-runoff-focus-head">
      <div><div class="hybrid-section-title">Closest tested runoff</div><h3>${escapeHtml(matchup.candidates.join(" vs "))}</h3></div>
      <span class="hybrid-status-chip">${escapeHtml(model.statusLabel)} · ${model.pollsterCount} pollsters</span>
    </div>
    <p class="hybrid-section-sub">Shared fieldwork window: ${escapeHtml(model.fieldworkLabel)} · ${matchup.observationCount} supporting source-reported observations.</p>
    <div class="hybrid-runoff-observations">
      ${matchup.observations.map(item => observationMarkup(item, matchup.candidates, item.sourceIndex === model.featuredObservation.sourceIndex)).join("")}
    </div>
    <section class="hybrid-common-section" aria-label="Common tested matchup information">
      <h3 class="hybrid-common-title">OTHER COMMON TESTED MATCHUPS</h3>
      <div class="hybrid-common-grid">${otherCommonMatchups.map(common => `
        <article class="hybrid-common-card">
          <h4>${escapeHtml(common.candidates.join(" vs "))}</h4>
          ${common.results.map(result => `<div class="hybrid-common-row"><span>${escapeHtml(result.pollster)}</span><strong>${number(result.margin)} pts</strong>${sourceLink(result.source_url, "Source", "", `Open ${result.pollster} source for ${common.candidates.join(" versus ")}`)}</div>`).join("")}
        </article>`).join("")}
      </div>
    </section>
    <p class="hybrid-disclosure">Second-round polling, not a forecast. Individual source-reported results and margins are shown separately; no average or probability is calculated. The featured result is the smallest absolute margin in the backend-selected matchup.</p>`;
  }

  function comparisonRows(items, max, label) {
    if (!items.length) return '<div class="hybrid-state is-compact">No supported rows in this update.</div>';
    return `<div class="hybrid-comparison-list">${items.map(item => `
      <div class="hybrid-comparison-row">
        <span>${escapeHtml(item.name)}</span>
        <span class="hybrid-track" aria-hidden="true"><span class="hybrid-fill" style="--hybrid-width:${(item.count / max * 100).toFixed(1)}%"></span></span>
        <span class="hybrid-comparison-value">${item.count} ${escapeHtml(label)}</span>
      </div>`).join("")}</div>`;
  }

  function renderMediaPanel(model) {
    if (model.state !== "ready") return summaryState(model);
    return `<div class="hybrid-media-layout">
      <section class="hybrid-media-block">
        <h3 class="hybrid-section-title">Accepted election-news activity · latest ${model.activityWindowDays} calendar days</h3>
        <p class="hybrid-section-sub">${countLabel(model.activityItemCount, "item")} in displayed ${model.activityWindowDays}-day activity window; zero-count calendar days remain visible.</p>
        <div class="hybrid-activity-chart" role="img" aria-label="Accepted election-news items for each of the latest 14 calendar days">
          ${activityBars(model.dailyActivity, model.activityMax)}
        </div>
        <div class="hybrid-axis-labels"><span>${formatDay(model.dailyActivity[0].key)}</span><span>${formatDay(model.dailyActivity.at(-1).key)}</span></div>
        <div class="visually-hidden">${model.dailyActivity.map(day => `${formatDay(day.key)}: ${day.count} accepted items`).join("; ")}</div>
      </section>
      <section class="hybrid-media-block">
        <h3 class="hybrid-section-title">Publisher contribution · accepted election news · ${model.windowDays}-day source window</h3>
        <p class="hybrid-section-sub">Contribution to accepted election-news items within monitored publisher sources.</p>
        ${comparisonRows(model.publisherContribution, model.publisherMax, "items")}
      </section>
      <section class="hybrid-media-block">
        <h3 class="hybrid-section-title">Latest source-linked headlines</h3>
        <div class="hybrid-headlines">${model.headlines.map(item => `
          <article class="hybrid-headline">
            <div class="hybrid-headline-meta"><time datetime="${escapeAttribute(item.published_at)}">${escapeHtml(formatNewsDateTime(item.published_at))}</time><span class="hybrid-headline-publisher">${escapeHtml(item.publisher)}</span></div>
            <a href="${escapeAttribute(safeSourceUrl(item.url))}" target="_blank" rel="noopener noreferrer" lang="fr">${escapeHtml(item.headline)} <span aria-hidden="true">↗</span></a>
          </article>`).join("")}</div>
      </section>
      <section class="hybrid-media-block">
        <h3 class="hybrid-section-title">Top six candidate-watch associations · ${model.windowDays}-day source window</h3>
        <p class="hybrid-section-sub">Based on candidate_watch records, a separate dataset from accepted election news; a candidate counts at most once per underlying article.</p>
        ${comparisonRows(model.candidateCoverage.slice(0, 6), model.candidateMax, "items")}
      </section>
    </div>
    <p class="hybrid-disclosure">${model.electionNewsCount} accepted election-news items · ${model.windowDays}-day source window. ${model.candidateWatchCount} candidate-watch records · ${model.windowDays}-day source window. ${model.healthyFeedCount}/${model.configuredPublisherCount} publisher feeds ready. Candidate figures are publisher-item associations, not popularity, support, momentum or public attention.</p>`;
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
      <div class="hybrid-tabs" role="tablist" aria-label="Signal Board detail views">
        ${viewOrder.map(key => `<button class="hybrid-tab" id="hybrid-tab-${key}" type="button" role="tab"
          data-hybrid-view="${key}" aria-controls="hybrid-panel-${key}" aria-selected="false" tabindex="-1">${views[key].label}</button>`).join("")}
      </div>
      <section class="hybrid-panel" id="hybrid-panel-runoff" role="tabpanel" aria-labelledby="hybrid-tab-runoff">${renderRunoffPanel(models.runoff)}</section>
      <section class="hybrid-panel" id="hybrid-panel-media" role="tabpanel" aria-labelledby="hybrid-tab-media">${renderMediaPanel(models.media)}</section>
      <section class="hybrid-panel" id="hybrid-panel-agenda" role="tabpanel" aria-labelledby="hybrid-tab-agenda">${renderAgendaPanel(models.agenda)}</section>
      <section class="hybrid-panel" id="hybrid-panel-claims" role="tabpanel" aria-labelledby="hybrid-tab-claims">${renderClaimsPanel(models.claims)}</section>
    </section>`;
  }

  function setActiveSignalView(view, options = {}) {
    if (!views[view]) view = "media";
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
    if (options.scrollWorkspace) scrollWorkspaceIfNeeded();
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
    state.scrollOnNextHash = source === "card";
    if (window.location.hash === views[view].hash) {
      setActiveSignalView(view, { scrollWorkspace: state.scrollOnNextHash });
      state.scrollOnNextHash = false;
      return;
    }
    window.location.hash = views[view].hash;
  }

  function scrollWorkspaceIfNeeded() {
    const workspace = mount.querySelector("[data-hybrid-workspace]");
    if (!workspace) return;
    const rect = workspace.getBoundingClientRect();
    if (rect.top >= 0 && rect.top < window.innerHeight * .82) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    workspace.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
  }

  function bindInteractions() {
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
  }

  function renderAll() {
    try {
      const models = buildAllViewModels();
      mount.innerHTML = `<div class="hybrid-board-head"><h2 class="hybrid-board-title">Signal Board</h2><div class="hybrid-board-note">Four summaries · one shared focus workspace</div></div>
        ${renderSummaryGrid(models)}
        ${renderFocusWorkspace(models)}`;
      bindInteractions();
      setActiveSignalView(state.activeView);
    } catch (error) {
      console.error("Hybrid Signal Board render failed", error);
      mount.innerHTML = `<div class="hybrid-state is-error" role="alert">The Signal Board could not render. Existing dashboard evidence remains available below.</div>`;
    }
  }

  function handleSignalHashChange() {
    const next = hashToView.get(window.location.hash) || "media";
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

  retainLegacyComparison();
  renderAll();
  window.addEventListener("hashchange", handleSignalHashChange);
  document.addEventListener("hybrid:dataset", renderAll);

  window.hybridDashboard = Object.freeze({
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
