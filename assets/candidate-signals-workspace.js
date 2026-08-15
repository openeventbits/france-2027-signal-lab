(() => {
  "use strict";


  const translate = (key, fallback) => {
    const localizer = globalThis.FR27I18N;

    return localizer && typeof localizer.t === "function"
      ? localizer.t(key)
      : fallback;
  };

  const MISSING = "Not published";
  const NOT_TESTED = "Not tested";
  const stateNames = new Set([
    "loading",
    "ready",
    "empty",
    "unavailable"
  ]);

  function createElement(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function hasValue(value) {
    return value !== null && value !== undefined && value !== "";
  }

  function numberText(value) {
    return hasValue(value) && Number.isFinite(Number(value))
      ? String(Number(value))
      : MISSING;
  }

  function groupedNumberText(value) {
    if (!hasValue(value) || !Number.isFinite(Number(value))) return MISSING;
    return String(Math.trunc(Number(value))).replace(
      /\B(?=(\d{3})+(?!\d))/g,
      ","
    );
  }

  function percentageText(value, ratio = false) {
    if (!hasValue(value) || !Number.isFinite(Number(value))) return MISSING;
    const amount = ratio ? Number(value) * 100 : Number(value);
    const rounded = Math.round((amount + Number.EPSILON) * 1000) / 1000;
    return `${rounded}%`;
  }

  function compactPercentageText(value, ratio = false) {
    if (!hasValue(value) || !Number.isFinite(Number(value))) return MISSING;
    const amount = ratio ? Number(value) * 100 : Number(value);
    const rounded = Math.round((amount + Number.EPSILON) * 10) / 10;
    return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
  }

  function rangeText(minimum, maximum) {
    if (!hasValue(minimum) || !hasValue(maximum)) return MISSING;
    return `${percentageText(minimum)}–${percentageText(maximum)}`;
  }

  function percentageNumber(value, ratio = true) {
    if (!hasValue(value) || !Number.isFinite(Number(value))) return null;
    const amount = ratio ? Number(value) * 100 : Number(value);
    return Math.max(0, Math.min(100, amount));
  }

  function formatDisplayDate(value, includeTime = false) {
    if (!hasValue(value)) return MISSING;
    const source = String(value);
    const normalized = /^\d{4}-\d{2}-\d{2}$/.test(source)
      ? `${source}T00:00:00Z`
      : source;
    const date = new Date(normalized);
    if (!Number.isFinite(date.getTime())) return source;

    const dateText = new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      timeZone: "UTC"
    }).format(date);

    if (!includeTime) return dateText;

    const timeText = new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "UTC"
    }).format(date);

    return `${dateText} · ${timeText} UTC`;
  }

  function formatDateRange(startValue, endValue) {
    if (!hasValue(startValue) && !hasValue(endValue)) return MISSING;
    if (!hasValue(startValue)) return formatDisplayDate(endValue);
    if (!hasValue(endValue)) return formatDisplayDate(startValue);

    const start = new Date(`${startValue}T00:00:00Z`);
    const end = new Date(`${endValue}T00:00:00Z`);

    if (
      Number.isFinite(start.getTime()) &&
      Number.isFinite(end.getTime()) &&
      start.getUTCFullYear() === end.getUTCFullYear() &&
      start.getUTCMonth() === end.getUTCMonth()
    ) {
      const monthYear = new Intl.DateTimeFormat("en-GB", {
        month: "short",
        year: "numeric",
        timeZone: "UTC"
      }).format(end);

      return `${start.getUTCDate()}–${end.getUTCDate()} ${monthYear}`;
    }

    return `${formatDisplayDate(startValue)} – ${formatDisplayDate(endValue)}`;
  }

  function humanizeStatus(value) {
    if (!hasValue(value)) return MISSING;
    return String(value)
      .split("_")
      .filter(Boolean)
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  }

  function counted(value, singular, plural = `${singular}s`) {
    if (!hasValue(value)) return MISSING;
    const number = Number(value);
    if (!Number.isFinite(number)) return MISSING;
    return `${numberText(number)} ${number === 1 ? singular : plural}`;
  }

  function pollValue(candidate) {
    const polling = candidate.polling;
    if (polling?.evidence_state !== "reported") return NOT_TESTED;
    if (hasValue(polling.selected_hypothesis_score)) {
      return percentageText(polling.selected_hypothesis_score);
    }
    return rangeText(polling.range_min, polling.range_max);
  }

  function initials(name) {
    return String(name || "")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(part => part.charAt(0))
      .join("")
      .toUpperCase();
  }

  function portrait(candidate, resolvePortrait, className) {
    const frame = createElement("span", className);
    const fallback = createElement(
      "span",
      "candidate-signals-portrait-fallback",
      initials(candidate.candidate_name)
    );
    fallback.setAttribute("aria-hidden", "true");
    frame.append(fallback);

    const path = typeof resolvePortrait === "function"
      ? resolvePortrait(candidate.candidate_id)
      : null;
    if (typeof path === "string" && path) {
      const image = createElement("img", "candidate-signals-portrait-image");
      image.src = path;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      image.addEventListener("error", () => image.remove(), { once: true });
      frame.append(image);
    }
    return frame;
  }

  function safeUrl(value) {
    if (typeof value !== "string" || !value) return null;
    try {
      const parsed = new URL(value);
      return parsed.protocol === "http:" || parsed.protocol === "https:"
        ? parsed.href
        : null;
    } catch (_error) {
      return null;
    }
  }

  function regionHeader(title, note = null, className = "") {
    const header = createElement(
      "header",
      `candidate-signals-region-header${className ? ` ${className}` : ""}`
    );

    header.append(
      createElement("h2", "candidate-signals-region-title", title)
    );

    if (note) {
      header.append(
        createElement("span", "candidate-signals-region-note", note)
      );
    }

    return header;
  }

  function evidenceLine(label, value) {
    const row = createElement("div", "candidate-signals-evidence-line");
    row.append(
      createElement("span", "candidate-signals-evidence-label", label),
      createElement(
        "span",
        "candidate-signals-evidence-value",
        hasValue(value) ? String(value) : MISSING
      )
    );
    return row;
  }

  function evidenceGroup(title, lines) {
    const group = createElement("div", "candidate-signals-evidence-group");
    if (title) {
      group.append(
        createElement("h4", "candidate-signals-evidence-group-title", title)
      );
    }
    lines.forEach(item => group.append(evidenceLine(item[0], item[1])));
    return group;
  }

  function isRaceAttentionEvidence(evidence) {
    return [
      "observed_positive",
      "observed_zero",
      "unavailable"
    ].includes(String(evidence?.observation_state || ""));
  }

  function hasAttentionObservation(evidence) {
    if (isRaceAttentionEvidence(evidence)) {
      return [
        "observed_positive",
        "observed_zero"
      ].includes(String(evidence?.observation_state || ""));
    }

    return evidence?.evidence_state === "reported";
  }

  function visibilityLines(candidate) {
    const campaign = candidate.campaign_attention;
    const general = candidate.general_visibility;

    if (isRaceAttentionEvidence(campaign)) {
      return [
        [
          "Race records",
          campaign ? numberText(campaign.record_count) : MISSING
        ],
        [
          "Race exposures",
          campaign ? numberText(campaign.exposure_count) : MISSING
        ],
        [
          "Race attention share",
          campaign ? percentageText(campaign.share, true) : MISSING
        ],
        [
          "General political records",
          general ? numberText(general.record_count) : MISSING
        ]
      ];
    }

    return [
      [
        "Campaign/election records",
        campaign ? numberText(campaign.record_count) : MISSING
      ],
      [
        "Campaign/election share",
        campaign ? percentageText(campaign.share, true) : MISSING
      ],
      [
        "General records",
        general ? numberText(general.record_count) : MISSING
      ],
      [
        "General share",
        general ? percentageText(general.share, true) : MISSING
      ]
    ];
  }

  function scrutinyLines(candidate) {
    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;
    return [
      ["14 days · BY", latest ? numberText(latest.by_count) : MISSING],
      ["14 days · ABOUT", latest ? numberText(latest.about_count) : MISSING],
      [translate("candidate.scrutiny.archive_by", "Archive · BY"), archive ? numberText(archive.by_count) : MISSING],
      ["Archive · ABOUT", archive ? numberText(archive.about_count) : MISSING]
    ];
  }

  function pollLines(candidate, metadata) {
    const polling = candidate.polling;
    const reported = polling?.evidence_state === "reported";
    const pollPackage = metadata?.featured_polling_package;
    const lines = [
      ["Selected estimate", reported
        ? percentageText(polling.selected_hypothesis_score)
        : NOT_TESTED],
      ["Published range", reported
        ? rangeText(polling.range_min, polling.range_max)
        : NOT_TESTED]
    ];

    if (pollPackage) {
      if (hasValue(pollPackage.pollster)) {
        lines.push(["Pollster", pollPackage.pollster]);
      }
      if (
        hasValue(pollPackage.fieldwork_start) ||
        hasValue(pollPackage.fieldwork_end)
      ) {
        lines.push([
          "Field dates",
          [pollPackage.fieldwork_start, pollPackage.fieldwork_end]
            .filter(hasValue)
            .join(" – ")
        ]);
      }
      if (hasValue(pollPackage.sample_size)) {
        lines.push(["Sample", numberText(pollPackage.sample_size)]);
      }
    }
    if (polling && hasValue(polling.hypothesis_count)) {
      lines.push(["Hypotheses", numberText(polling.hypothesis_count)]);
    }
    if (Array.isArray(pollPackage?.source_urls)) {
      const count = pollPackage.source_urls.filter(safeUrl).length;
      if (count) lines.push(["Published sources", numberText(count)]);
    }
    return lines;
  }

  function structureLines(evidence, prefix) {
    const concentration = evidence?.concentration;
    return [
      [`${prefix} publishers`, evidence
        ? numberText(evidence.publisher_count)
        : MISSING],
      [`${prefix} active days`, evidence
        ? numberText(evidence.active_day_count)
        : MISSING],
      [`${prefix} story clusters`, evidence
        ? numberText(evidence.story_cluster_count)
        : MISSING],
      [`${prefix} leading publisher`, concentration &&
        hasValue(concentration.leading_publisher)
        ? concentration.leading_publisher
        : MISSING],
      [`${prefix} publisher concentration`, concentration
        ? percentageText(concentration.leading_publisher_share, true)
        : MISSING],
      [`${prefix} story concentration`, concentration
        ? percentageText(concentration.leading_story_share, true)
        : MISSING]
    ];
  }

  function statePresentation(message, statusRole = false) {
    const node = createElement("div", "candidate-signals-state", message);
    if (statusRole) {
      node.setAttribute("role", "status");
      node.setAttribute("aria-live", "polite");
    }
    return node;
  }

  function candidateSecondary(candidate) {
    const campaign = candidate.campaign_attention;
    const general = candidate.general_visibility;
    if (!campaign && !general) return MISSING;
    return [
      `Campaign / election ${campaign
        ? numberText(campaign.record_count)
        : MISSING}`,
      `General ${general ? numberText(general.record_count) : MISSING}`
    ].join(" · ");
  }

  function candidateFact(label, value, className = "") {
    const fact = createElement(
      "span",
      `candidate-signals-candidate-fact${className ? ` ${className}` : ""}`
    );
    fact.append(
      createElement(
        "span",
        "candidate-signals-candidate-fact-label",
        label
      ),
      createElement(
        "strong",
        "candidate-signals-candidate-fact-value",
        value
      )
    );
    return fact;
  }

  function candidateMonitor(candidates, selectedId, options, chooseCandidate) {
    const section = createElement(
      "section",
      "candidate-signals-panel candidate-signals-monitor"
    );
    section.setAttribute("aria-labelledby", "candidate-signals-monitor-title");

    const header = regionHeader(translate("candidate.candidate_monitor", "CANDIDATE MONITOR"));
    header.querySelector("h2").id = "candidate-signals-monitor-title";

    const tools = createElement("div", "candidate-signals-monitor-tools");
    const label = createElement(
      "label",
      "candidate-signals-search-label",
      "Search candidate"
    );
    label.setAttribute("for", "candidate-signals-search");

    const input = createElement("input", "candidate-signals-search-input");
    input.id = "candidate-signals-search";
    input.type = "search";
    input.placeholder = "Search candidate…";
    input.autocomplete = "off";
    input.setAttribute("aria-controls", "candidate-signals-monitor-list");

    const filterButton = createElement(
      "button",
      "candidate-signals-filter-button"
    );
    filterButton.type = "button";
    filterButton.setAttribute("aria-pressed", "false");
    filterButton.setAttribute(
      "aria-label",
      "Show main candidates only"
    );
    filterButton.title = "Show main candidates only";

    const filterGlyph = createElement(
      "span",
      "candidate-signals-filter-glyph"
    );
    filterGlyph.setAttribute("aria-hidden", "true");
    filterButton.append(filterGlyph);

    tools.append(label, input, filterButton);

    const list = createElement("div", "candidate-signals-monitor-list");
    list.id = "candidate-signals-monitor-list";
    list.setAttribute("aria-label", "Published candidates");

    const noMatches = createElement(
      "p",
      "candidate-signals-monitor-empty",
      "No matching candidates."
    );
    noMatches.hidden = true;
    noMatches.setAttribute("aria-live", "polite");

    candidates.forEach(candidate => {
      const selected = candidate.candidate_id === selectedId;
      const button = createElement(
        "button",
        `candidate-signals-candidate-button${selected ? " is-selected" : ""}`
      );
      button.type = "button";
      button.dataset.candidateSignalsCandidate = candidate.candidate_id;
      button.dataset.candidateSearch = candidate.candidate_name.toLowerCase();
      button.dataset.candidateTier = String(
        candidate.candidacy?.display_tier || ""
      ).toLowerCase();
      button.setAttribute("aria-pressed", String(selected));

      const top = createElement("span", "candidate-signals-candidate-top");
      const identity = createElement(
        "span",
        "candidate-signals-candidate-identity"
      );
      identity.append(
        portrait(
          candidate,
          options.resolvePortrait,
          "candidate-signals-portrait candidate-signals-monitor-portrait"
        )
      );

      const copy = createElement("span", "candidate-signals-candidate-copy");
      copy.append(
        createElement(
          "span",
          "candidate-signals-candidate-name",
          candidate.candidate_name
        ),
        createElement(
          "span",
          "candidate-signals-candidate-secondary",
          candidateSecondary(candidate)
        )
      );

      const tier = candidate.candidacy?.display_tier;
      if (hasValue(tier)) {
        copy.append(
          createElement(
            "span",
            "candidate-signals-candidate-tier",
            String(tier).toUpperCase()
          )
        );
      }
      identity.append(copy);

      const metric = createElement(
        "span",
        "candidate-signals-candidate-metric"
      );
      const pollText = pollValue(candidate);
      metric.append(
        createElement(
          "strong",
          `candidate-signals-candidate-poll${
            pollText === MISSING || pollText === NOT_TESTED
              ? " is-unpublished"
              : ""
          }`,
          pollText
        )
      );
      top.append(identity, metric);

      const campaign = candidate.campaign_attention;
      const raceAttention = isRaceAttentionEvidence(campaign);
      const latest = candidate.scrutiny?.latest_14_days;
      const evidence = createElement(
        "span",
        "candidate-signals-candidate-evidence"
      );
      evidence.append(
        candidateFact(
          raceAttention ? "Race attention" : "Attention",
          campaign
            ? percentageText(campaign.share, true)
            : "Not published",
          "candidate-signals-candidate-attention"
        ),
        candidateFact(
          raceAttention ? "Exposures" : "Records",
          campaign
            ? numberText(
                raceAttention
                  ? campaign.exposure_count
                  : campaign.record_count
              )
            : "Not published",
          "candidate-signals-candidate-records"
        ),
        candidateFact(
          "Scrutiny · 14 days",
          latest
            ? `${numberText(latest.about_count)} about · ${numberText(
              latest.by_count
            )} by`
            : "Not published",
          "candidate-signals-candidate-scrutiny"
        )
      );

      button.append(top, evidence);
      button.addEventListener("click", () => {
        chooseCandidate(candidate.candidate_id, true);
      });
      button.addEventListener("keydown", event => {
        const buttons = Array.from(
          list.querySelectorAll(".candidate-signals-candidate-button")
        ).filter(item => !item.hidden);
        const index = buttons.indexOf(button);
        if (index < 0 || !buttons.length) return;

        let target = null;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") {
          target = buttons[(index + 1) % buttons.length];
        } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
          target = buttons[(index - 1 + buttons.length) % buttons.length];
        } else if (event.key === "Home") {
          target = buttons[0];
        } else if (event.key === "End") {
          target = buttons[buttons.length - 1];
        }

        if (!target) return;
        event.preventDefault();
        chooseCandidate(target.dataset.candidateSignalsCandidate, true);
      });

      list.append(button);
    });

    let mainOnly = false;

    const applyFilters = () => {
      const term = String(input.value || "").trim().toLowerCase();
      let visible = 0;

      list.querySelectorAll(".candidate-signals-candidate-button").forEach(
        button => {
          const matchesText = (
            !term ||
            button.dataset.candidateSearch.includes(term)
          );

          const matchesTier = (
            !mainOnly ||
            button.dataset.candidateTier === "main"
          );

          const matches = matchesText && matchesTier;
          button.hidden = !matches;

          if (matches) visible += 1;
        }
      );

      noMatches.hidden = visible !== 0;
    };

    input.addEventListener("input", applyFilters);

    filterButton.addEventListener("click", () => {
      mainOnly = !mainOnly;

      filterButton.className = (
        `candidate-signals-filter-button${
          mainOnly ? " is-active" : ""
        }`
      );

      filterButton.setAttribute(
        "aria-pressed",
        String(mainOnly)
      );

      const description = mainOnly
        ? "Show all candidates"
        : "Show main candidates only";

      filterButton.setAttribute("aria-label", description);
      filterButton.title = description;

      applyFilters();
    });

    section.append(header, tools, list, noMatches);
    return section;
  }

  function candidacyEvidence(candidate) {
    const section = createElement(
      "section",
      "candidate-signals-candidacy-evidence"
    );
    section.append(
      createElement(
        "h3",
        "candidate-signals-subsection-title",
        "CANDIDACY EVIDENCE"
      )
    );

    const candidacy = candidate.candidacy;
    if (!candidacy) {
      section.append(
        createElement(
          "p",
          "candidate-signals-development-empty",
          "No candidacy evidence is currently published."
        )
      );
      return section;
    }

    const statusRow = createElement(
      "div",
      "candidate-signals-candidacy-status-row"
    );
    statusRow.append(
      createElement(
        "span",
        "candidate-signals-candidacy-status",
        humanizeStatus(candidacy.status)
      )
    );

    if (hasValue(candidacy.display_tier)) {
      statusRow.append(
        createElement(
          "span",
          "candidate-signals-candidacy-tier",
          String(candidacy.display_tier).toUpperCase()
        )
      );
    }

    const note = createElement(
      "p",
      "candidate-signals-candidacy-note",
      candidacy.status_note || MISSING
    );

    const source = createElement(
      "p",
      "candidate-signals-candidacy-source"
    );
    source.append(
      createElement(
        "span",
        "candidate-signals-candidacy-source-label",
        "Source"
      ),
      createElement(
        "strong",
        "candidate-signals-candidacy-source-value",
        [
          candidacy.source_publisher,
          formatDisplayDate(candidacy.source_date)
        ].filter(hasValue).join(" · ") || MISSING
      )
    );

    section.append(statusRow, note, source);

    const href = safeUrl(candidacy.source_url);
    if (href) {
      const link = createElement(
        "a",
        "candidate-signals-source-link",
        "View candidacy source →"
      );
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      section.append(link);
    }

    return section;
  }

  function developmentContent(candidate, detailed = false) {
    const development = candidate.latest_development;
    if (!development || !hasValue(development.headline)) {
      return [
        createElement(
          "p",
          "candidate-signals-development-empty",
          "No source-linked development is currently published."
        )
      ];
    }

    const content = [
      createElement(
        detailed ? "h4" : "strong",
        "candidate-signals-development-headline",
        development.headline || MISSING
      ),
      evidenceLine("Source", development.publisher),
      evidenceLine(
        "Published",
        formatDisplayDate(development.published_at, true)
      )
    ];
    const href = safeUrl(development.url);
    if (href) {
      const link = createElement(
        "a",
        "candidate-signals-source-link",
        "Open source ↗"
      );
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      content.push(link);
    } else {
      content.push(evidenceLine("Source link", MISSING));
    }
    return content;
  }

  function analysisLatestDevelopment(candidate) {
    const section = createElement(
      "section",
      "candidate-signals-latest-development"
    );
    section.append(
      createElement(
        "h3",
        "candidate-signals-subsection-title",
        "LATEST DEVELOPMENT"
      )
    );

    const development = candidate.latest_development;
    if (!development || !hasValue(development.headline)) {
      section.append(
        createElement(
          "p",
          "candidate-signals-development-empty",
          "No source-linked development is currently published."
        )
      );
      return section;
    }

    if (hasValue(development.coverage_scope)) {
      section.append(
        createElement(
          "span",
          "candidate-signals-development-scope",
          String(development.coverage_scope).toUpperCase()
        )
      );
    }

    section.append(
      createElement(
        "strong",
        "candidate-signals-development-headline",
        development.headline
      ),
      createElement(
        "p",
        "candidate-signals-development-meta",
        [
          development.publisher,
          formatDisplayDate(development.published_at, true)
        ].filter(hasValue).join(" · ")
      )
    );

    const href = safeUrl(development.url);
    if (href) {
      const link = createElement(
        "a",
        "candidate-signals-source-link",
        "Open latest source →"
      );
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      section.append(link);
    } else {
      section.append(evidenceLine("Source link", MISSING));
    }

    return section;
  }

  function dossierLatestDevelopment(candidate) {
    const section = createElement(
      "section",
      "candidate-signals-dossier-card candidate-signals-dossier-development"
    );
    section.append(
      createElement(
        "h3",
        "candidate-signals-dossier-card-title",
        "LATEST DEVELOPMENT"
      )
    );
    const body = createElement(
      "div",
      "candidate-signals-dossier-development-body"
    );
    body.append(...developmentContent(candidate, true));
    section.append(body);
    return section;
  }

  function scopeComposition(candidate) {
    const counts = candidate.campaign_attention?.scope_counts;
    const values = ["campaign", "election", "general"].map(key => {
      const value = counts?.[key];
      if (!hasValue(value)) return null;
      const number = Number(value);
      return Number.isFinite(number) && number >= 0 ? number : null;
    });
    const complete = values.every(value => value !== null);
    const anyPublished = values.some(value => value !== null);
    const total = complete
      ? values.reduce((sum, value) => sum + value, 0)
      : null;
    return { values, complete, anyPublished, total };
  }

  function scopeLegendRow(label, count, total, tone, complete = true) {
    const row = createElement(
      "div",
      `candidate-signals-scope-row is-${tone}`
    );
    const percentage = complete && total > 0 && count !== null
      ? compactPercentageText(count / total, true)
      : MISSING;

    const labelWrap = createElement(
      "span",
      "candidate-signals-scope-label"
    );
    labelWrap.append(
      createElement(
        "span",
        `candidate-signals-scope-dot is-${tone}`
      ),
      createElement("span", "", label)
    );

    row.append(
      createElement(
        "strong",
        "candidate-signals-scope-count",
        count === null ? MISSING : numberText(count)
      ),
      createElement(
        "span",
        "candidate-signals-scope-percentage",
        percentage
      ),
      labelWrap
    );
    return row;
  }

  function summaryCard(title, className = "") {
    const card = createElement(
      "article",
      `candidate-signals-analysis-card${className ? ` ${className}` : ""}`
    );
    card.append(
      createElement(
        "h3",
        "candidate-signals-analysis-card-title",
        title
      )
    );
    return card;
  }

  function summaryMeta(label, value) {
    const row = createElement("div", "candidate-signals-summary-meta");
    row.append(
      createElement(
        "span",
        "candidate-signals-summary-meta-label",
        label
      ),
      createElement(
        "span",
        "candidate-signals-summary-meta-value",
        value
      )
    );
    return row;
  }

  function pollFact(label, value) {
    const fact = createElement(
      "span",
      "candidate-signals-poll-fact"
    );
    fact.append(
      createElement(
        "span",
        "candidate-signals-poll-fact-label",
        label
      ),
      createElement(
        "strong",
        "candidate-signals-poll-fact-value",
        hasValue(value) ? String(value) : MISSING
      )
    );
    return fact;
  }

  function pollSummaryCard(candidate, metadata) {
    const card = summaryCard(
      "POLL EVIDENCE",
      "candidate-signals-poll-summary"
    );
    const poll = candidate.polling;
    const pollPackage = metadata?.featured_polling_package;
    const reported = poll?.evidence_state === "reported";
    const hasRange = reported &&
      hasValue(poll.range_min) &&
      hasValue(poll.range_max);
    const hasSelected = reported &&
      hasValue(poll.selected_hypothesis_score);

    const primaryText = !reported
      ? NOT_TESTED
      : hasSelected
        ? percentageText(poll.selected_hypothesis_score)
        : hasRange
          ? rangeText(poll.range_min, poll.range_max)
          : MISSING;

    card.append(
      createElement(
        "strong",
        `candidate-signals-summary-primary${
          reported ? "" : " is-textual"
        }`,
        primaryText
      )
    );

    if (hasRange) {
      const minimum = Number(poll.range_min);
      const maximum = Number(poll.range_max);
      const selected = hasSelected
        ? Number(poll.selected_hypothesis_score)
        : null;
      const span = maximum - minimum;
      const markerPosition = selected === null
        ? null
        : span === 0
          ? 50
          : Math.max(
            0,
            Math.min(100, ((selected - minimum) / span) * 100)
          );

      const gauge = createElement(
        "div",
        "candidate-signals-poll-gauge"
      );
      gauge.setAttribute(
        "aria-label",
        selected === null
          ? `Published range ${rangeText(minimum, maximum)}`
          : `Published range ${rangeText(
            minimum,
            maximum
          )}; selected estimate ${percentageText(selected)}`
      );
      gauge.append(
        createElement(
          "span",
          "candidate-signals-poll-gauge-kicker",
          "PUBLISHED RANGE"
        )
      );

      const track = createElement(
        "span",
        "candidate-signals-poll-gauge-track"
      );
      track.append(
        createElement(
          "span",
          "candidate-signals-poll-gauge-range"
        )
      );

      if (markerPosition !== null) {
        const marker = createElement(
          "span",
          "candidate-signals-poll-gauge-marker"
        );
        marker.style.left = (
          `clamp(4px, ${markerPosition}%, calc(100% - 4px))`
        );
        track.append(marker);
      }

      const labels = createElement(
        "span",
        `candidate-signals-poll-gauge-labels${
          minimum === maximum ? " is-single" : ""
        }`
      );

      if (minimum === maximum) {
        labels.append(
          createElement("span", "", percentageText(minimum))
        );
      } else {
        labels.append(
          createElement("span", "", percentageText(minimum)),
          createElement("span", "", percentageText(maximum))
        );
      }

      gauge.append(track, labels);
      card.append(gauge);
    } else {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          "No accepted first-round test in the current polling window."
        )
      );
    }

    if (reported) {
      const facts = createElement(
        "div",
        "candidate-signals-poll-facts"
      );
      facts.append(
        pollFact(
          "POLLSTER",
          pollPackage?.pollster || MISSING
        ),
        pollFact(
          "FIELDWORK",
          formatDateRange(
            pollPackage?.fieldwork_start,
            pollPackage?.fieldwork_end
          )
        ),
        pollFact(
          "HYPOTHESES",
          hasValue(poll?.hypothesis_count)
            ? `${numberText(poll.hypothesis_count)} hypotheses`
            : MISSING
        ),
        pollFact(
          "SAMPLE",
          hasValue(pollPackage?.sample_size)
            ? `N=${groupedNumberText(pollPackage.sample_size)}`
            : MISSING
        )
      );
      card.append(facts);
    }

    return card;
  }

  function attentionVisualRow(
    label,
    evidence,
    tone,
    scaleMaximum
  ) {
    const row = createElement(
      "div",
      `candidate-signals-attention-row is-${tone}`
    );
    const reported = hasAttentionObservation(evidence);
    const share = reported
      ? percentageNumber(evidence.share, true)
      : null;
    const comparativeWidth = (
      share === null ||
      !Number.isFinite(Number(scaleMaximum)) ||
      Number(scaleMaximum) <= 0
    )
      ? 0
      : Math.max(
        0,
        Math.min(100, (share / Number(scaleMaximum)) * 100)
      );

    const head = createElement(
      "div",
      "candidate-signals-attention-row-head"
    );
    head.append(
      createElement(
        "span",
        "candidate-signals-attention-label",
        label
      ),
      createElement(
        "strong",
        `candidate-signals-attention-share${
          share === null ? " is-unpublished" : ""
        }`,
        share === null ? MISSING : percentageText(evidence.share, true)
      )
    );

    const raceAttention = isRaceAttentionEvidence(evidence);
    const compactParts = reported
      ? raceAttention
        ? [
          hasValue(evidence.exposure_count)
            ? `${numberText(evidence.exposure_count)} EXP`
            : null,
          hasValue(evidence.publisher_count)
            ? `${numberText(evidence.publisher_count)} PUB`
            : null,
          hasValue(evidence.story_count)
            ? `${numberText(evidence.story_count)} ${
              Number(evidence.story_count) === 1 ? "STORY" : "STORIES"
            }`
            : null
        ].filter(Boolean)
        : [
          hasValue(evidence.record_count)
            ? `${numberText(evidence.record_count)} REC`
            : null,
          hasValue(evidence.publisher_count)
            ? `${numberText(evidence.publisher_count)} PUB`
            : null,
          hasValue(evidence.active_day_count)
            ? `${numberText(evidence.active_day_count)} ${
              Number(evidence.active_day_count) === 1 ? "DAY" : "DAYS"
            }`
            : null
        ].filter(Boolean)
      : [];

    const detail = createElement(
      "span",
      "candidate-signals-attention-detail",
      reported ? compactParts.join(" · ") : "No current evidence"
    );
    if (reported) {
      detail.setAttribute(
        "aria-label",
        (
          raceAttention
            ? [
              counted(evidence.exposure_count, "exposure"),
              hasValue(evidence.publisher_count)
                ? counted(evidence.publisher_count, "publisher")
                : null,
              hasValue(evidence.story_count)
                ? counted(evidence.story_count, "story")
                : null
            ]
            : [
              counted(evidence.record_count, "record"),
              hasValue(evidence.publisher_count)
                ? counted(evidence.publisher_count, "publisher")
                : null,
              hasValue(evidence.active_day_count)
                ? counted(evidence.active_day_count, "active day")
                : null
            ]
        ).filter(Boolean).join(", ")
      );
    }

    const track = createElement(
      "span",
      `candidate-signals-attention-track${
        share === null ? " is-unavailable" : ""
      }`
    );
    track.setAttribute("aria-hidden", "true");
    const fill = createElement(
      "span",
      "candidate-signals-attention-fill"
    );
    fill.style.width = `${comparativeWidth}%`;
    if (share !== null && share > 0) {
      fill.className += " has-value";
    }
    track.append(fill);

    row.append(head, detail, track);
    return row;
  }

  function attentionSummaryCard(candidate) {
    const raceAttention = isRaceAttentionEvidence(
      candidate.campaign_attention
    );
    const card = summaryCard(
      raceAttention ? "RACE ATTENTION" : "CAMPAIGN ATTENTION",
      "candidate-signals-attention-summary"
    );

    const campaignShare = hasAttentionObservation(
      candidate.campaign_attention
    )
      ? percentageNumber(candidate.campaign_attention.share, true)
      : null;

    if (raceAttention) {
      const scaleMaximum = campaignShare !== null
        ? campaignShare
        : 0;
      const visual = createElement(
        "div",
        "candidate-signals-attention-visual"
      );
      visual.append(
        attentionVisualRow(
          "Race attention",
          candidate.campaign_attention,
          "primary",
          scaleMaximum
        )
      );
      card.append(visual);
      return card;
    }

    const generalShare = candidate.general_visibility?.evidence_state ===
      "reported"
      ? percentageNumber(candidate.general_visibility.share, true)
      : null;
    const publishedShares = [campaignShare, generalShare]
      .filter(value => value !== null);
    const scaleMaximum = publishedShares.length
      ? Math.max(...publishedShares)
      : 0;

    const visual = createElement(
      "div",
      "candidate-signals-attention-visual"
    );
    visual.append(
      attentionVisualRow(
        raceAttention ? "Race attention" : "Campaign / election",
        candidate.campaign_attention,
        "primary",
        scaleMaximum
      ),
      attentionVisualRow(
        raceAttention
          ? "General political coverage"
          : "General visibility",
        candidate.general_visibility,
        "general",
        scaleMaximum
      )
    );
    card.append(visual);
    return card;
  }

  function compositionSegment(
    tone,
    count,
    total,
    complete
  ) {
    const segment = createElement(
      "span",
      `candidate-signals-composition-segment is-${tone}`
    );
    const ratio = (
      complete &&
      total !== null &&
      total > 0 &&
      count !== null
    )
      ? count / total
      : 0;
    segment.style.width = `${Math.max(
      0,
      Math.min(100, ratio * 100)
    )}%`;
    return segment;
  }

  function scopeCompositionCard(candidate) {
    const raceAttention = isRaceAttentionEvidence(
      candidate.campaign_attention
    );
    const card = summaryCard(
      raceAttention ? "COVERAGE COUNTS" : "COVERAGE MIX",
      "candidate-signals-composition-card"
    );

    if (raceAttention) {
      const race = candidate.campaign_attention;
      const general = candidate.general_visibility;

      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          [
            `${numberText(race?.record_count)} race records`,
            `${numberText(race?.exposure_count)} race exposures`,
            `${numberText(race?.story_count)} race stories`,
            `${numberText(general?.record_count)} general political records`
          ].join(" · ")
        )
      );

      return card;
    }

    const composition = scopeComposition(candidate);
    const [campaign, election, general] = composition.values;

    if (!composition.anyPublished) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          "No campaign/election evidence observed in the current period."
        )
      );
      return card;
    }

    const visual = createElement(
      "div",
      "candidate-signals-composition-visual"
    );

    const totalLine = createElement(
      "div",
      "candidate-signals-composition-total-line"
    );
    totalLine.append(
      createElement(
        "strong",
        "candidate-signals-composition-total",
        composition.complete
          ? numberText(composition.total)
          : MISSING
      ),
      createElement(
        "span",
        "candidate-signals-composition-unit",
        "records"
      )
    );

    const stack = createElement(
      "div",
      `candidate-signals-composition-stack${
        composition.complete ? "" : " is-incomplete"
      }`
    );
    stack.setAttribute(
      "aria-label",
      composition.complete
        ? `Coverage composition: ${numberText(campaign)} campaign, ${
          numberText(election)
        } election, ${numberText(general)} general`
        : "Coverage composition is incomplete"
    );
    stack.append(
      compositionSegment(
        "campaign",
        campaign,
        composition.total,
        composition.complete
      ),
      compositionSegment(
        "election",
        election,
        composition.total,
        composition.complete
      ),
      compositionSegment(
        "general",
        general,
        composition.total,
        composition.complete
      )
    );

    const legend = createElement(
      "div",
      `candidate-signals-composition-legend${
        composition.complete ? "" : " is-incomplete"
      }`
    );
    legend.append(
      scopeLegendRow(
        "Campaign",
        campaign,
        composition.total,
        "campaign",
        composition.complete
      ),
      scopeLegendRow(
        "Election",
        election,
        composition.total,
        "election",
        composition.complete
      ),
      scopeLegendRow(
        "General",
        general,
        composition.total,
        "general",
        composition.complete
      )
    );

    visual.append(totalLine, stack, legend);
    card.append(visual);
    return card;
  }

  function scrutinyMatrixCell(value, periodClass = "") {
    const numeric = hasValue(value) && Number.isFinite(Number(value))
      ? Number(value)
      : null;
    const stateClass = numeric === null
      ? "is-unpublished"
      : numeric === 0
        ? "is-zero"
        : "is-active";

    return createElement(
      "strong",
      `candidate-signals-scrutiny-cell ${periodClass} ${stateClass}`,
      numeric === null ? MISSING : numberText(numeric)
    );
  }

  function scrutinySummaryCard(candidate) {
    const card = summaryCard(
      "SCRUTINY",
      "candidate-signals-scrutiny-summary"
    );
    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;

    if (!latest && !archive) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          "No scrutiny evidence is currently published."
        )
      );
      return card;
    }

    const matrix = createElement(
      "div",
      "candidate-signals-scrutiny-matrix"
    );
    matrix.append(
      createElement("span", "candidate-signals-scrutiny-corner", ""),
      createElement("span", "candidate-signals-scrutiny-column", "ABOUT"),
      createElement("span", "candidate-signals-scrutiny-column", "BY"),
      createElement("span", "candidate-signals-scrutiny-column", "REVIEWS"),
      createElement(
        "span",
        "candidate-signals-scrutiny-row-label is-current",
        "14 DAYS"
      ),
      scrutinyMatrixCell(
        latest ? latest.about_count : null,
        "is-current"
      ),
      scrutinyMatrixCell(
        latest ? latest.by_count : null,
        "is-current"
      ),
      scrutinyMatrixCell(
        latest ? latest.review_count : null,
        "is-current"
      ),
      createElement(
        "span",
        "candidate-signals-scrutiny-row-label is-archive",
        "ARCHIVE"
      ),
      scrutinyMatrixCell(
        archive ? archive.about_count : null,
        "is-archive"
      ),
      scrutinyMatrixCell(
        archive ? archive.by_count : null,
        "is-archive"
      ),
      scrutinyMatrixCell(
        archive ? archive.review_count : null,
        "is-archive"
      )
    );
    card.append(matrix);

    const newestDate = latest?.newest_review_date || archive?.newest_review_date;
    card.append(
      createElement(
        "span",
        "candidate-signals-scrutiny-foot",
        `LATEST REVIEW · ${
          newestDate ? formatDisplayDate(newestDate) : MISSING
        }`
      )
    );

    return card;
  }

  function evidenceStructureStat(label, value) {
    const stat = createElement(
      "div",
      "candidate-signals-evidence-structure-stat"
    );
    stat.append(
      createElement(
        "strong",
        "candidate-signals-evidence-structure-value",
        value
      ),
      createElement(
        "span",
        "candidate-signals-evidence-structure-label",
        label
      )
    );
    return stat;
  }

  function evidenceRatioRow(
    label,
    detail,
    ratio,
    tone = "primary"
  ) {
    const row = createElement(
      "div",
      `candidate-signals-evidence-ratio is-${tone}`
    );
    const copy = createElement(
      "div",
      "candidate-signals-evidence-ratio-copy"
    );
    copy.append(
      createElement(
        "span",
        "candidate-signals-evidence-ratio-label",
        label
      ),
      createElement(
        "span",
        "candidate-signals-evidence-ratio-detail",
        detail
      )
    );

    const track = createElement(
      "span",
      `candidate-signals-evidence-ratio-track${
        ratio === null ? " is-unavailable" : ""
      }`
    );
    track.setAttribute("aria-hidden", "true");
    const fill = createElement(
      "span",
      "candidate-signals-evidence-ratio-fill"
    );
    fill.style.width = ratio === null
      ? "0%"
      : `${Math.max(0, Math.min(100, ratio))}%`;
    track.append(fill);

    row.append(copy, track);
    return row;
  }

  function evidenceMatchBasis(candidate) {
    const evidence = candidate.campaign_attention;
    const total = evidence?.record_count;
    const headline = evidence?.headline_match_count;
    const summaryOnly = evidence?.summary_only_match_count;
    const published = [
      total,
      headline,
      summaryOnly
    ].every(hasValue);

    const row = createElement(
      "div",
      "candidate-signals-match-basis"
    );
    const copy = createElement(
      "div",
      "candidate-signals-evidence-ratio-copy"
    );
    copy.append(
      createElement(
        "span",
        "candidate-signals-evidence-ratio-label",
        "Match basis"
      ),
      createElement(
        "span",
        "candidate-signals-evidence-ratio-detail",
        published
          ? `${numberText(headline)} headline · ${numberText(
            summaryOnly
          )} summary-only`
          : MISSING
      )
    );

    const track = createElement(
      "span",
      `candidate-signals-match-basis-track${
        published ? "" : " is-unavailable"
      }`
    );
    track.setAttribute("aria-hidden", "true");

    const basisTotal = published
      ? Number(headline) + Number(summaryOnly)
      : 0;

    if (published && basisTotal > 0) {
      const headlineShare = (Number(headline) / basisTotal) * 100;
      const summaryShare = (Number(summaryOnly) / basisTotal) * 100;
      const headlineFill = createElement(
        "span",
        "candidate-signals-match-basis-headline"
      );
      headlineFill.style.width = `${headlineShare}%`;
      const summaryFill = createElement(
        "span",
        "candidate-signals-match-basis-summary"
      );
      summaryFill.style.width = `${summaryShare}%`;
      track.append(headlineFill, summaryFill);
    }

    row.append(copy, track);
    return row;
  }

  function evidenceStructureBreakdown(candidate, metadata) {
    const section = createElement(
      "section",
      "candidate-signals-evidence-structure"
    );
    const campaign = candidate.campaign_attention;
    const raceAttention = isRaceAttentionEvidence(campaign);
    const reported = hasAttentionObservation(campaign);

    const head = createElement(
      "div",
      "candidate-signals-evidence-structure-head"
    );
    head.append(
      createElement(
        "h3",
        "candidate-signals-subsection-title",
        "EVIDENCE STRUCTURE"
      )
    );

    const period = raceAttention
      ? metadata?.activeFieldVisibility?.race_attention?.current_period
      : metadata?.visibility?.current_period;
    head.append(
      createElement(
        "span",
        "candidate-signals-evidence-structure-period",
        period
          ? formatDateRange(period.start_date, period.end_date)
          : "Current published period"
      )
    );

    section.append(head);

    if (!reported) {
      section.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          raceAttention
            ? "No race attention evidence observed in the current period."
            : "No campaign/election evidence observed in the current period."
        )
      );
      return section;
    }

    const stats = createElement(
      "div",
      "candidate-signals-evidence-structure-stats"
    );
    if (raceAttention) {
      stats.append(
        evidenceStructureStat(
          "Records",
          numberText(campaign.record_count)
        ),
        evidenceStructureStat(
          "Exposures",
          numberText(campaign.exposure_count)
        ),
        evidenceStructureStat(
          "Publishers",
          numberText(campaign.publisher_count)
        ),
        evidenceStructureStat(
          "Stories",
          numberText(campaign.story_count)
        )
      );
      section.append(stats);
      return section;
    }

    stats.append(
      evidenceStructureStat(
        "Records",
        numberText(campaign.record_count)
      ),
      evidenceStructureStat(
        "Publishers",
        numberText(campaign.publisher_count)
      ),
      evidenceStructureStat(
        "Active days",
        numberText(campaign.active_day_count)
      ),
      evidenceStructureStat(
        "Story clusters",
        numberText(campaign.story_cluster_count)
      )
    );

    const concentration = campaign.concentration;
    const ratios = createElement(
      "div",
      "candidate-signals-evidence-structure-ratios"
    );
    ratios.append(
      evidenceMatchBasis(candidate),
      evidenceRatioRow(
        "Top publisher",
        concentration
          ? [
            concentration.leading_publisher || MISSING,
            Number(campaign.record_count) > 0
              ? `${numberText(
                concentration.leading_publisher_record_count
              )}/${numberText(campaign.record_count)}`
              : counted(
                concentration.leading_publisher_record_count,
                "record"
              ),
            percentageText(
              concentration.leading_publisher_share,
              true
            )
          ].join(" · ")
          : MISSING,
        concentration
          ? percentageNumber(
            concentration.leading_publisher_share,
            true
          )
          : null,
        "publisher"
      ),
      evidenceRatioRow(
        "Top story concentration",
        concentration
          ? `${
            Number(campaign.record_count) > 0
              ? `${numberText(
                concentration.leading_story_record_count
              )}/${numberText(campaign.record_count)}`
              : counted(
                concentration.leading_story_record_count,
                "record"
              )
          } · ${percentageText(
            concentration.leading_story_share,
            true
          )}`
          : MISSING,
        concentration
          ? percentageNumber(
            concentration.leading_story_share,
            true
          )
          : null,
        "story"
      )
    );

    section.append(stats, ratios);
    return section;
  }


  function wikipediaSignedPercent(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return MISSING;
    return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}%`;
  }

  function wikipediaAttentionFlagLabel(value) {
    const labels = {
      sustained_rise: "SUSTAINED RISE",
      sustained_decline: "SUSTAINED DECLINE",
      event_amplified: "EVENT AMPLIFIED",
      stable: "STABLE",
      low_attention: "LOW ATTENTION"
    };

    return labels[value] || (
      hasValue(value)
        ? String(value).replace(/_/g, " ").toUpperCase()
        : MISSING
    );
  }

  function wikipediaAttentionTone(value) {
    if (value === "sustained_rise") return "rise";
    if (value === "sustained_decline") return "decline";
    if (value === "event_amplified") return "event";
    if (value === "low_attention") return "low";
    return "stable";
  }

  function wikipediaChangeTone(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric === 0) {
      return "stable";
    }
    return numeric > 0 ? "rise" : "decline";
  }

  function wikipediaCompactNumber(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return MISSING;

    const absolute = Math.abs(numeric);

    if (absolute >= 1000000) {
      const amount = numeric / 1000000;
      return `${
        Math.abs(amount) >= 10
          ? amount.toFixed(0)
          : amount.toFixed(1).replace(/\.0$/, "")
      }M`;
    }

    if (absolute >= 1000) {
      const amount = numeric / 1000;
      return `${
        Math.abs(amount) >= 10
          ? amount.toFixed(0)
          : amount.toFixed(1).replace(/\.0$/, "")
      }K`;
    }

    return groupedNumberText(numeric);
  }

  function wikipediaShortDate(value) {
    if (!hasValue(value)) return MISSING;

    const date = new Date(`${value}T00:00:00Z`);

    if (!Number.isFinite(date.getTime())) {
      return String(value);
    }

    return new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      month: "short",
      timeZone: "UTC"
    }).format(date);
  }

  function wikipediaNiceStep(value) {
    const numeric = Number(value);

    if (!Number.isFinite(numeric) || numeric <= 0) {
      return 1;
    }

    const exponent = Math.floor(Math.log10(numeric));
    const magnitude = 10 ** exponent;
    const normalized = numeric / magnitude;

    const factor =
      normalized <= 1
        ? 1
        : normalized <= 2
          ? 2
          : normalized <= 2.5
            ? 2.5
            : normalized <= 5
              ? 5
              : 10;

    return factor * magnitude;
  }

  function wikipediaAttentionMetric(
    label,
    value,
    className = ""
  ) {
    const metric = createElement(
      "div",
      `candidate-signals-wikipedia-metric${
        className ? ` ${className}` : ""
      }`
    );

    metric.append(
      createElement(
        "span",
        "candidate-signals-wikipedia-metric-label",
        label
      ),
      createElement(
        "strong",
        "candidate-signals-wikipedia-metric-value",
        value
      )
    );

    return metric;
  }

  function wikipediaAttentionStateMetric(flag, tone) {
    const metric = createElement(
      "div",
      "candidate-signals-wikipedia-metric is-state"
    );

    metric.append(
      createElement(
        "span",
        "candidate-signals-wikipedia-metric-label",
        "STATE"
      ),
      createElement(
        "span",
        `candidate-signals-wikipedia-pattern is-${tone}`,
        wikipediaAttentionFlagLabel(flag)
      )
    );

    return metric;
  }

  function wikipediaSvgElement(tagName, className = "") {
    const node = document.createElementNS(
      "http://www.w3.org/2000/svg",
      tagName
    );

    if (className) {
      node.setAttribute("class", className);
    }

    return node;
  }

  function wikipediaAttentionLineChart(
    recent,
    candidate,
    peak,
    latestPoint
  ) {
    const block = createElement(
      "div",
      "candidate-signals-wikipedia-line-block"
    );

    block.append(
      createElement(
        "span",
        "candidate-signals-wikipedia-chart-title",
        "DAILY PAGEVIEWS"
      )
    );

    const svg = wikipediaSvgElement(
      "svg",
      "candidate-signals-wikipedia-svg"
    );

    const width = 640;
    const height = 104;
    const margin = {
      top: 7,
      right: 10,
      bottom: 22,
      left: 43
    };

    const plotWidth =
      width - margin.left - margin.right;
    const plotHeight =
      height - margin.top - margin.bottom;

    const maximum = Math.max(
      0,
      ...recent.map(point => Number(point.views))
    );

    const step = wikipediaNiceStep(maximum / 3);

    const axisMaximum =
      maximum > 0
        ? Math.max(
          step,
          Math.ceil(maximum / step) * step
        )
        : 1;

    const xFor = index =>
      margin.left +
      (
        recent.length <= 1
          ? 0
          : (
            index /
            (recent.length - 1)
          ) * plotWidth
      );

    const yFor = value =>
      margin.top +
      plotHeight -
      (
        Math.max(0, Number(value)) /
        axisMaximum
      ) * plotHeight;

    svg.setAttribute(
      "viewBox",
      `0 0 ${width} ${height}`
    );
    svg.setAttribute(
      "preserveAspectRatio",
      "none"
    );
    svg.setAttribute(
      "role",
      "img"
    );
    svg.setAttribute(
      "aria-label",
      `French Wikipedia daily pageviews for ${
        candidate.candidate_name
      }, ${formatDisplayDate(
        recent[0].date
      )} through ${formatDisplayDate(
        latestPoint.date
      )}. Thirty-day peak ${
        groupedNumberText(peak.views)
      } views on ${formatDisplayDate(
        peak.date
      )}.`
    );
    for (
      let tick = 0;
      tick <= axisMaximum + (step / 10);
      tick += step
    ) {
      const y = yFor(tick);

      const grid = wikipediaSvgElement(
        "line",
        "candidate-signals-wikipedia-gridline"
      );
      grid.setAttribute("x1", margin.left);
      grid.setAttribute("x2", width - margin.right);
      grid.setAttribute("y1", y);
      grid.setAttribute("y2", y);
      svg.append(grid);

      const label = wikipediaSvgElement(
        "text",
        "candidate-signals-wikipedia-y-label"
      );
      label.setAttribute("x", margin.left - 7);
      label.setAttribute("y", y + 3);
      label.setAttribute("text-anchor", "end");
      label.textContent = wikipediaCompactNumber(tick);
      svg.append(label);
    }

    const xLabelIndices = [
      0,
      6,
      12,
      18,
      24,
      recent.length - 1
    ];

    [...new Set(xLabelIndices)]
      .filter(
        index =>
          index >= 0 &&
          index < recent.length
      )
      .forEach((index, position, values) => {
        const label = wikipediaSvgElement(
          "text",
          "candidate-signals-wikipedia-x-label"
        );

        label.setAttribute("x", xFor(index));
        label.setAttribute("y", height - 5);
        label.setAttribute(
          "text-anchor",
          position === 0
            ? "start"
            : position === values.length - 1
              ? "end"
              : "middle"
        );
        label.textContent =
          wikipediaShortDate(recent[index].date);
        svg.append(label);
      });

    const line = wikipediaSvgElement(
      "polyline",
      "candidate-signals-wikipedia-line"
    );

    line.setAttribute(
      "points",
      recent.map(
        (point, index) =>
          `${xFor(index).toFixed(2)},${
            yFor(point.views).toFixed(2)
          }`
      ).join(" ")
    );

    svg.append(line);

    recent.forEach((point, index) => {
      const classes = [
        "candidate-signals-wikipedia-point"
      ];

      if (point.date === peak.date) {
        classes.push("is-peak");
      }

      if (index === recent.length - 1) {
        classes.push("is-latest");
      }

      const marker = wikipediaSvgElement(
        "circle",
        classes.join(" ")
      );

      marker.setAttribute("cx", xFor(index));
      marker.setAttribute("cy", yFor(point.views));
      marker.setAttribute(
        "r",
        point.date === peak.date
          ? 4
          : index === recent.length - 1
            ? 3.5
            : 2.7
      );

      const pointLabel =
        `${formatDisplayDate(
          point.date
        )} · ${groupedNumberText(
          point.views
        )} views`;

      marker.setAttribute(
        "aria-label",
        pointLabel
      );

      const pointTitle =
        wikipediaSvgElement("title");
      pointTitle.textContent = pointLabel;
      marker.append(pointTitle);

      svg.append(marker);
    });

    block.append(svg);
    return block;
  }

  function wikipediaAttentionPanel(
    candidate,
    attentionState
  ) {
    const section = createElement(
      "section",
      "candidate-signals-wikipedia-attention"
    );

    const head = createElement(
      "div",
      "candidate-signals-wikipedia-head"
    );

    const heading = createElement(
      "div",
      "candidate-signals-wikipedia-heading"
    );

    const headingTitle = createElement(
      "h3",
      "candidate-signals-subsection-title",
      "WIKIPEDIA ATTENTION · 30 DAYS"
    );

    heading.append(
      headingTitle,
      createElement(
        "span",
        "candidate-signals-wikipedia-source",
        "French Wikipedia daily pageviews"
      )
    );

    head.append(heading);

    if (attentionState?.status === "loading") {
      section.append(
        head,
        createElement(
          "p",
          "candidate-signals-wikipedia-state",
          "Loading published Wikimedia attention…"
        )
      );
      return section;
    }

    const payload =
      attentionState?.status === "ready"
        ? attentionState.payload
        : null;

    const methodology = payload?.methodology;

    const interpretation =
      methodology?.interpretation ||
      "French Wikipedia pageviews measure article-reading attention.";

    const exclusions =
      Array.isArray(methodology?.not_measures)
        ? methodology.not_measures.filter(hasValue)
        : [];

    const methodologyNote =
      exclusions.length
        ? `${interpretation} They do not measure ${
          exclusions.join(", ")
        }.`
        : interpretation;

    headingTitle.setAttribute(
      "title",
      methodologyNote
    );

    const record = payload?.candidates?.find(
      item =>
        item.candidate_id === candidate.candidate_id
    );

    if (!record) {
      section.append(
        head,
        createElement(
          "p",
          "candidate-signals-wikipedia-state",
          "Published Wikipedia attention is unavailable for this candidate."
        )
      );
      return section;
    }

    const validSeries = record.daily_series.filter(
      point =>
        point &&
        /^\d{4}-\d{2}-\d{2}$/.test(
          String(point.date || "")
        ) &&
        Number.isFinite(Number(point.views)) &&
        Number(point.views) >= 0
    );

    const recent = validSeries.slice(-30);

    if (recent.length !== 30) {
      section.append(
        head,
        createElement(
          "p",
          "candidate-signals-wikipedia-state",
          "A complete 30-day Wikipedia attention series is unavailable."
        )
      );
      return section;
    }

    const peak = recent.reduce(
      (best, point) =>
        !best ||
        Number(point.views) > Number(best.views)
          ? point
          : best,
      null
    );

    const latestPoint =
      recent[recent.length - 1];

    const periodDate =
      payload?.period?.data_as_of ||
      latestPoint.date;

    head.append(
      createElement(
        "span",
        "candidate-signals-wikipedia-asof",
        `DATA THROUGH ${formatDisplayDate(
          periodDate
        ).toUpperCase()}`
      )
    );

    const tone =
      wikipediaAttentionTone(
        record.interpretation_flag
      );

    const primary = createElement(
      "div",
      "candidate-signals-wikipedia-primary-metrics"
    );

    primary.append(
      wikipediaAttentionMetric(
        "LATEST 7D",
        groupedNumberText(
          record.latest_7_views
        )
      ),
      wikipediaAttentionMetric(
        "PREVIOUS 7D",
        groupedNumberText(
          record.previous_7_views
        )
      ),
      wikipediaAttentionMetric(
        "7D CHANGE",
        wikipediaSignedPercent(
          record.change_7_pct
        ),
        `is-${wikipediaChangeTone(
          record.change_7_pct
        )}`
      ),
      wikipediaAttentionMetric(
        "30D PEAK",
        groupedNumberText(peak.views)
      ),
      wikipediaAttentionMetric(
        "PEAK DATE",
        formatDisplayDate(peak.date)
      ),
      wikipediaAttentionStateMetric(
        record.interpretation_flag,
        tone
      )
    );

    const chart =
      wikipediaAttentionLineChart(
        recent,
        candidate,
        peak,
        latestPoint
      );

    const secondary = createElement(
      "div",
      "candidate-signals-wikipedia-secondary-metrics"
    );

    secondary.append(
      wikipediaAttentionMetric(
        "PEAK-REMOVED 7D",
        wikipediaSignedPercent(
          record.change_7_peak_removed_pct
        ),
        `is-${wikipediaChangeTone(
          record.change_7_peak_removed_pct
        )}`
      ),
      wikipediaAttentionMetric(
        "28D TOTAL",
        groupedNumberText(
          record.latest_28_views
        )
      ),
      wikipediaAttentionMetric(
        "28D CHANGE",
        wikipediaSignedPercent(
          record.change_28_pct
        ),
        `is-${wikipediaChangeTone(
          record.change_28_pct
        )}`
      )
    );


    section.append(
      head,
      primary,
      chart,
      secondary
    );

    return section;
  }


  function selectedAnalysis(candidate, metadata, attentionState) {
    const section = createElement(
      "section",
      "candidate-signals-panel candidate-signals-analysis"
    );
    section.setAttribute("aria-labelledby", "candidate-signals-analysis-title");
    section.setAttribute("aria-live", "polite");
    section.setAttribute("aria-atomic", "true");

    const updateDate = metadata?.evidence_dates?.news;
    const header = regionHeader(
      translate("candidate.selected_analysis", "SELECTED ANALYSIS"),
      hasValue(updateDate)
        ? `Updated ${formatDisplayDate(updateDate)}`
        : null
    );
    header.querySelector("h2").id = "candidate-signals-analysis-title";

    const cards = createElement("div", "candidate-signals-analysis-cards");
    cards.append(
      pollSummaryCard(candidate, metadata),
      attentionSummaryCard(candidate),
      scopeCompositionCard(candidate),
      scrutinySummaryCard(candidate)
    );

    const lower = createElement("div", "candidate-signals-analysis-lower");
    lower.append(
      candidacyEvidence(candidate),
      analysisLatestDevelopment(candidate)
    );

    const body = createElement("div", "candidate-signals-analysis-body");
    body.append(
      cards,
      evidenceStructureBreakdown(candidate, metadata),
      lower,
      wikipediaAttentionPanel(
        candidate,
        attentionState
      )
    );
    section.append(header, body);
    return section;
  }

  function dossierMetric(
    label,
    primary,
    notes = [],
    className = ""
  ) {
    const metric = createElement(
      "article",
      `candidate-signals-dossier-metric${
        className ? ` ${className}` : ""
      }`
    );
    metric.append(
      createElement(
        "span",
        "candidate-signals-dossier-metric-label",
        label
      ),
      createElement(
        "strong",
        "candidate-signals-dossier-metric-value",
        primary
      )
    );

    const noteList = Array.isArray(notes) ? notes : [notes];
    const noteWrap = createElement(
      "span",
      "candidate-signals-dossier-metric-notes"
    );
    noteList.filter(hasValue).forEach(note => {
      noteWrap.append(
        createElement(
          "span",
          "candidate-signals-dossier-metric-note",
          note
        )
      );
    });
    metric.append(noteWrap);
    return metric;
  }

  function dossierStructureStat(label, value) {
    const stat = createElement(
      "div",
      "candidate-signals-structure-stat"
    );
    stat.append(
      createElement(
        "strong",
        "candidate-signals-structure-stat-value",
        value
      ),
      createElement(
        "span",
        "candidate-signals-structure-stat-label",
        label
      )
    );
    return stat;
  }

  function dossierPollLines(candidate, metadata) {
    const polling = candidate.polling;
    const reported = polling?.evidence_state === "reported";
    const pollPackage = metadata?.featured_polling_package;
    const sourceCount = Array.isArray(pollPackage?.source_urls)
      ? pollPackage.source_urls.filter(safeUrl).length
      : null;
    const hasPointEstimate = (
      reported && hasValue(polling.selected_hypothesis_score)
    );
    const hasPublishedRange = (
      reported &&
      (
        hasValue(polling.range_min) ||
        hasValue(polling.range_max)
      )
    );

    return [
      ["Point estimate", hasPointEstimate
        ? percentageText(polling.selected_hypothesis_score)
        : hasPublishedRange
          ? "Range only"
          : reported
            ? MISSING
            : NOT_TESTED],
      ["Published range", reported
        ? rangeText(polling.range_min, polling.range_max)
        : NOT_TESTED],
      ["Pollster", pollPackage?.pollster || MISSING],
      ["Field dates", formatDateRange(
        pollPackage?.fieldwork_start,
        pollPackage?.fieldwork_end
      )],
      ["Sample", hasValue(pollPackage?.sample_size)
        ? groupedNumberText(pollPackage.sample_size)
        : MISSING],
      ["Hypotheses", reported && hasValue(polling.hypothesis_count)
        ? numberText(polling.hypothesis_count)
        : reported
          ? MISSING
          : NOT_TESTED],
      ["Published sources", hasValue(sourceCount)
        ? numberText(sourceCount)
        : MISSING]
    ];
  }

  function dossierStructureLines(evidence) {
    if (isRaceAttentionEvidence(evidence)) {
      return [
        ["Records", evidence
          ? numberText(evidence.record_count)
          : MISSING],
        ["Exposures", evidence
          ? numberText(evidence.exposure_count)
          : MISSING],
        ["Publishers", evidence
          ? numberText(evidence.publisher_count)
          : MISSING],
        ["Stories", evidence
          ? numberText(evidence.story_count)
          : MISSING]
      ];
    }

    const concentration = evidence?.concentration;
    return [
      ["Publishers", evidence
        ? numberText(evidence.publisher_count)
        : MISSING],
      ["Active days", evidence
        ? numberText(evidence.active_day_count)
        : MISSING],
      ["Story clusters", evidence
        ? numberText(evidence.story_cluster_count)
        : MISSING],
      ["Leading publisher", concentration && hasValue(
        concentration.leading_publisher
      ) ? concentration.leading_publisher : MISSING],
      ["Publisher concentration", concentration
        ? percentageText(
          concentration.leading_publisher_share,
          true
        )
        : MISSING],
      ["Story concentration", concentration
        ? percentageText(
          concentration.leading_story_share,
          true
        )
        : MISSING]
    ];
  }

  function dossierScrutinyLines(candidate) {
    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;
    const newestDate = (
      latest?.newest_review_date || archive?.newest_review_date
    );
    return [
      ["14 days · ABOUT", latest
        ? numberText(latest.about_count)
        : MISSING],
      ["14 days · BY", latest
        ? numberText(latest.by_count)
        : MISSING],
      ["14 days · Reviews", latest
        ? numberText(latest.review_count)
        : MISSING],
      ["Archive · ABOUT", archive
        ? numberText(archive.about_count)
        : MISSING],
      [translate("candidate.scrutiny.archive_by", "Archive · BY"), archive
        ? numberText(archive.by_count)
        : MISSING],
      ["Archive · Reviews", archive
        ? numberText(archive.review_count)
        : MISSING],
      ["Newest review", formatDisplayDate(newestDate)]
    ];
  }

  function compactEvidenceDetails(candidate, metadata) {
    const details = createElement(
      "details",
      "candidate-signals-dossier-details"
    );
    const summary = createElement(
      "summary",
      "candidate-signals-dossier-details-summary",
      "View full evidence details"
    );
    const content = createElement(
      "div",
      "candidate-signals-dossier-details-content"
    );
    content.append(
      evidenceGroup(
        "POLL EVIDENCE & SOURCE DETAILS",
        dossierPollLines(candidate, metadata)
      ),
      evidenceGroup(
        isRaceAttentionEvidence(candidate.campaign_attention)
          ? "RACE COVERAGE STRUCTURE"
          : "CAMPAIGN / ELECTION STRUCTURE",
        dossierStructureLines(candidate.campaign_attention)
      ),
      evidenceGroup(
        isRaceAttentionEvidence(candidate.campaign_attention)
          ? "GENERAL POLITICAL COVERAGE"
          : "GENERAL STRUCTURE",
        isRaceAttentionEvidence(candidate.campaign_attention)
          ? [
            ["Records", candidate.general_visibility
              ? numberText(candidate.general_visibility.record_count)
              : MISSING],
            ["Publishers", candidate.general_visibility
              ? numberText(candidate.general_visibility.publisher_count)
              : MISSING]
          ]
          : dossierStructureLines(candidate.general_visibility)
      ),
      evidenceGroup(
        "CLAIM SCRUTINY DETAIL",
        dossierScrutinyLines(candidate)
      )
    );
    details.append(summary, content);
    return details;
  }

  function dossierScopeCell(
    label,
    count,
    total,
    tone,
    complete = true
  ) {
    const cell = createElement(
      "div",
      `candidate-signals-dossier-scope-cell is-${tone}`
    );
    const percentage = complete && total > 0 && count !== null
      ? compactPercentageText(count / total, true)
      : MISSING;
    cell.append(
      createElement(
        "strong",
        "candidate-signals-dossier-scope-count",
        count === null ? MISSING : numberText(count)
      ),
      createElement(
        "span",
        "candidate-signals-dossier-scope-share",
        count === null ? "" : percentage
      ),
      createElement(
        "span",
        "candidate-signals-dossier-scope-label",
        label
      )
    );
    return cell;
  }

  function dossierVisibilityPanel(candidate) {
    const campaign = candidate.campaign_attention;
    const general = candidate.general_visibility;
    const raceAttention = isRaceAttentionEvidence(campaign);

    const card = createElement(
      "section",
      "candidate-signals-dossier-card candidate-signals-dossier-visibility"
    );
    card.append(
      createElement(
        "h3",
        "candidate-signals-dossier-card-title",
        raceAttention
          ? "RACE & GENERAL COVERAGE"
          : "VISIBILITY & COMPOSITION"
      )
    );

    if (raceAttention) {
      const campaignReported =
        hasAttentionObservation(campaign);
      const generalReported =
        general?.evidence_state === "reported";

      const totalLine = createElement(
        "div",
        "candidate-signals-dossier-visibility-total"
      );
      totalLine.append(
        createElement(
          "strong",
          "candidate-signals-dossier-visibility-total-value",
          campaignReported
            ? numberText(campaign.exposure_count)
            : MISSING
        ),
        createElement(
          "span",
          "candidate-signals-dossier-visibility-total-label",
          "Race exposures"
        )
      );
      card.append(totalLine);

      const summary = createElement(
        "div",
        "candidate-signals-dossier-visibility-summary"
      );
      summary.append(
        summaryMeta(
          "Race attention",
          campaignReported
            ? [
              counted(campaign.record_count, "record"),
              counted(campaign.exposure_count, "exposure"),
              percentageText(campaign.share, true)
            ].join(" · ")
            : "No current evidence"
        ),
        summaryMeta(
          "Race stories",
          campaignReported
            ? counted(campaign.story_count, "story")
            : "No current evidence"
        ),
        summaryMeta(
          "General political coverage",
          generalReported
            ? [
              counted(general.record_count, "record"),
              counted(general.publisher_count, "publisher")
            ].join(" · ")
            : "No current evidence"
        )
      );
      card.append(summary);
      return card;
    }

    const composition = scopeComposition(candidate);
    const [campaignCount, electionCount, generalCount] = composition.values;

    const totalLine = createElement(
      "div",
      "candidate-signals-dossier-visibility-total"
    );
    const totalText = composition.complete
      ? numberText(composition.total)
      : composition.anyPublished
        ? "Incomplete"
        : "No current evidence";
    totalLine.append(
      createElement(
        "strong",
        `candidate-signals-dossier-visibility-total-value${
          composition.complete ? "" : " is-textual"
        }`,
        totalText
      )
    );
    if (composition.anyPublished || composition.complete) {
      totalLine.append(
        createElement(
          "span",
          "candidate-signals-dossier-visibility-total-label",
          "Published records"
        )
      );
    }
    card.append(totalLine);

    const stack = createElement(
      "div",
      `candidate-signals-dossier-composition-stack${
        composition.complete ? "" : " is-incomplete"
      }`
    );
    stack.setAttribute("aria-hidden", "true");

    [
      [campaignCount, "campaign"],
      [electionCount, "election"],
      [generalCount, "general"]
    ].forEach(([count, tone]) => {
      const segment = createElement(
        "span",
        `candidate-signals-dossier-composition-segment is-${tone}`
      );
      const width = (
        composition.complete && composition.total > 0 && count !== null
      ) ? (count / composition.total) * 100 : 0;
      segment.style.width = `${Math.max(0, Math.min(100, width))}%`;
      stack.append(segment);
    });
    card.append(stack);

    const scopeGrid = createElement(
      "div",
      "candidate-signals-dossier-scope-grid"
    );
    scopeGrid.append(
      dossierScopeCell(
        "Campaign",
        campaignCount,
        composition.total,
        "campaign",
        composition.complete
      ),
      dossierScopeCell(
        "Election",
        electionCount,
        composition.total,
        "election",
        composition.complete
      ),
      dossierScopeCell(
        "General",
        generalCount,
        composition.total,
        "general",
        composition.complete
      )
    );
    card.append(scopeGrid);

    const summary = createElement(
      "div",
      "candidate-signals-dossier-visibility-summary"
    );
    const campaignReported = hasAttentionObservation(campaign);
    const generalReported = general?.evidence_state === "reported";
    summary.append(
      summaryMeta(
        "Campaign / election",
        campaignReported
          ? `${counted(campaign.record_count, "record")} · ${percentageText(
            campaign.share,
            true
          )}`
          : "No current evidence"
      ),
      summaryMeta(
        "General visibility",
        generalReported
          ? `${counted(general.record_count, "record")} · ${percentageText(
            general.share,
            true
          )}`
          : "No current evidence"
      )
    );
    card.append(summary);
    return card;
  }

  function dossierStructureRatio(label, detail, share, tone = "publisher") {
    const row = createElement(
      "div",
      `candidate-signals-dossier-structure-ratio is-${tone}`
    );
    const copy = createElement(
      "div",
      "candidate-signals-dossier-structure-ratio-copy"
    );
    copy.append(
      createElement(
        "span",
        "candidate-signals-dossier-structure-ratio-label",
        label
      ),
      createElement(
        "span",
        "candidate-signals-dossier-structure-ratio-detail",
        detail
      )
    );
    const track = createElement(
      "span",
      `candidate-signals-dossier-structure-track${
        percentageNumber(share, true) === null ? " is-unavailable" : ""
      }`
    );
    track.setAttribute("aria-hidden", "true");
    const fill = createElement(
      "span",
      "candidate-signals-dossier-structure-fill"
    );
    const width = percentageNumber(share, true);
    fill.style.width = width === null ? "0%" : `${width}%`;
    track.append(fill);
    row.append(copy, track);
    return row;
  }

  function evidenceStructurePanel(candidate) {
    const card = createElement(
      "section",
      "candidate-signals-dossier-card candidate-signals-dossier-structure"
    );
    card.append(
      createElement(
        "h3",
        "candidate-signals-dossier-card-title",
        "EVIDENCE STRUCTURE"
      )
    );

    const campaign = candidate.campaign_attention;
    const raceAttention = isRaceAttentionEvidence(campaign);
    const stats = createElement(
      "div",
      "candidate-signals-structure-stats"
    );

    if (raceAttention) {
      stats.append(
        dossierStructureStat(
          "Records",
          campaign && hasValue(campaign.record_count)
            ? numberText(campaign.record_count)
            : MISSING
        ),
        dossierStructureStat(
          "Exposures",
          campaign && hasValue(campaign.exposure_count)
            ? numberText(campaign.exposure_count)
            : MISSING
        ),
        dossierStructureStat(
          "Publishers",
          campaign && hasValue(campaign.publisher_count)
            ? numberText(campaign.publisher_count)
            : MISSING
        ),
        dossierStructureStat(
          "Stories",
          campaign && hasValue(campaign.story_count)
            ? numberText(campaign.story_count)
            : MISSING
        )
      );
      card.append(stats);
      return card;
    }

    stats.append(
      dossierStructureStat(
        "Records",
        campaign && hasValue(campaign.record_count)
          ? numberText(campaign.record_count)
          : MISSING
      ),
      dossierStructureStat(
        "Publishers",
        campaign && hasValue(campaign.publisher_count)
          ? numberText(campaign.publisher_count)
          : MISSING
      ),
      dossierStructureStat(
        "Active days",
        campaign && hasValue(campaign.active_day_count)
          ? numberText(campaign.active_day_count)
          : MISSING
      ),
      dossierStructureStat(
        "Story clusters",
        campaign && hasValue(campaign.story_cluster_count)
          ? numberText(campaign.story_cluster_count)
          : MISSING
      )
    );
    card.append(stats);

    const concentration = campaign?.concentration;
    const recordCount = campaign?.record_count;
    const ratios = createElement(
      "div",
      "candidate-signals-dossier-structure-ratios"
    );
    ratios.append(
      dossierStructureRatio(
        "Top publisher",
        concentration && hasValue(concentration.leading_publisher)
          ? [
            concentration.leading_publisher,
            hasValue(concentration.leading_publisher_record_count) &&
              hasValue(recordCount)
              ? `${numberText(
                concentration.leading_publisher_record_count
              )}/${numberText(recordCount)}`
              : null,
            percentageText(
              concentration.leading_publisher_share,
              true
            )
          ].filter(hasValue).join(" · ")
          : MISSING,
        concentration?.leading_publisher_share,
        "publisher"
      ),
      dossierStructureRatio(
        "Top story concentration",
        concentration && hasValue(concentration.leading_story_record_count)
          ? [
            hasValue(recordCount)
              ? `${numberText(
                concentration.leading_story_record_count
              )}/${numberText(recordCount)}`
              : numberText(concentration.leading_story_record_count),
            percentageText(
              concentration.leading_story_share,
              true
            )
          ].filter(hasValue).join(" · ")
          : MISSING,
        concentration?.leading_story_share,
        "story"
      )
    );
    card.append(ratios);
    return card;
  }

  function dossierScrutinyMetric(label, value) {
    const metric = createElement(
      "span",
      "candidate-signals-dossier-scrutiny-metric"
    );
    const valueClass = (
      hasValue(value) && Number.isFinite(Number(value)) && Number(value) === 0
    ) ? " is-zero" : "";
    metric.append(
      createElement(
        "strong",
        `candidate-signals-dossier-scrutiny-value${valueClass}`,
        hasValue(value) ? numberText(value) : MISSING
      ),
      createElement(
        "span",
        "candidate-signals-dossier-scrutiny-label",
        label
      )
    );
    return metric;
  }

  function dossierScrutinyPeriod(title, evidence, className) {
    const hasSignal = [
      evidence?.about_count,
      evidence?.by_count,
      evidence?.review_count
    ].some(value => (
      hasValue(value) &&
      Number.isFinite(Number(value)) &&
      Number(value) > 0
    ));
    const block = createElement(
      "section",
      `candidate-signals-dossier-scrutiny-block ${className}${
        hasSignal ? " has-signal" : ""
      }`
    );
    block.append(
      createElement(
        "h4",
        "candidate-signals-scrutiny-period-title",
        title
      )
    );
    const metrics = createElement(
      "div",
      "candidate-signals-dossier-scrutiny-metrics"
    );
    metrics.append(
      dossierScrutinyMetric("ABOUT", evidence?.about_count),
      dossierScrutinyMetric("BY", evidence?.by_count),
      dossierScrutinyMetric("REVIEWS", evidence?.review_count)
    );
    block.append(metrics);
    return block;
  }

  function scrutinyOverviewPanel(candidate) {
    const card = createElement(
      "section",
      "candidate-signals-dossier-card candidate-signals-dossier-scrutiny"
    );
    card.append(
      createElement(
        "h3",
        "candidate-signals-dossier-card-title",
        "SCRUTINY OVERVIEW"
      )
    );

    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;
    const newestDate = (
      latest?.newest_review_date || archive?.newest_review_date
    );
    const grid = createElement(
      "div",
      "candidate-signals-dossier-scrutiny-grid"
    );
    grid.append(
      dossierScrutinyPeriod("14 DAYS", latest, "is-current"),
      dossierScrutinyPeriod("ARCHIVE", archive, "is-archive")
    );

    const review = createElement(
      "section",
      "candidate-signals-dossier-scrutiny-block is-review"
    );
    review.append(
      createElement(
        "h4",
        "candidate-signals-scrutiny-period-title",
        "LATEST REVIEW"
      ),
      createElement(
        "strong",
        "candidate-signals-dossier-review-date",
        formatDisplayDate(newestDate)
      ),
      createElement(
        "span",
        "candidate-signals-dossier-review-note",
        "Published review date"
      )
    );
    grid.append(review);
    card.append(grid);
    return card;
  }

  function dossierLatestDevelopment(candidate) {
    const section = createElement(
      "section",
      "candidate-signals-dossier-card candidate-signals-dossier-development"
    );
    section.append(
      createElement(
        "h3",
        "candidate-signals-dossier-card-title",
        "LATEST DEVELOPMENT"
      )
    );

    const development = candidate.latest_development;
    if (!development || !hasValue(development.headline)) {
      section.append(
        createElement(
          "p",
          "candidate-signals-development-empty",
          "No source-linked development is currently published."
        )
      );
      return section;
    }

    if (hasValue(development.coverage_scope)) {
      section.append(
        createElement(
          "span",
          "candidate-signals-dossier-development-scope",
          String(development.coverage_scope).toUpperCase()
        )
      );
    }

    section.append(
      createElement(
        "h4",
        "candidate-signals-development-headline",
        development.headline
      ),
      createElement(
        "p",
        "candidate-signals-dossier-development-meta",
        [
          development.publisher,
          formatDisplayDate(development.published_at, true)
        ].filter(hasValue).join(" · ")
      )
    );

    const href = safeUrl(development.url);
    if (href) {
      const link = createElement(
        "a",
        "candidate-signals-source-link",
        "Open latest source →"
      );
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      section.append(link);
    } else {
      section.append(evidenceLine("Source link", MISSING));
    }
    return section;
  }

  function candidateDossier(candidate, metadata, options) {
    const section = createElement(
      "aside",
      "candidate-signals-panel candidate-signals-dossier"
    );
    section.setAttribute("aria-labelledby", "candidate-signals-dossier-title");
    const header = regionHeader(translate("candidate.candidate_dossier", "CANDIDATE DOSSIER"));
    header.querySelector("h2").id = "candidate-signals-dossier-title";

    const headerAction = createElement(
      "button",
      "candidate-signals-region-action",
      "View full evidence →"
    );
    headerAction.type = "button";

    headerAction.addEventListener("click", () => {
      const details = section.querySelector(
        ".candidate-signals-dossier-details"
      );
      if (!details) return;
      details.open = true;
      details.scrollIntoView({
        behavior: "smooth",
        block: "nearest"
      });
      details.querySelector("summary")?.focus();
    });
    header.append(headerAction);

    const body = createElement("div", "candidate-signals-dossier-body");
    const identity = createElement(
      "div",
      "candidate-signals-dossier-identity"
    );
    identity.append(
      portrait(
        candidate,
        options.resolvePortrait,
        "candidate-signals-portrait candidate-signals-dossier-portrait"
      )
    );

    const copy = createElement("div", "candidate-signals-dossier-name-block");
    copy.append(
      createElement(
        "span",
        "candidate-signals-kicker",
        "SELECTED CANDIDATE"
      ),
      createElement(
        "h3",
        "candidate-signals-dossier-name",
        candidate.candidate_name
      )
    );

    const badges = createElement(
      "div",
      "candidate-signals-dossier-badges"
    );
    const status = candidate.candidacy?.status;
    if (hasValue(status)) {
      badges.append(
        createElement(
          "span",
          "candidate-signals-dossier-status",
          humanizeStatus(status).toUpperCase()
        )
      );
    }
    const tier = candidate.candidacy?.display_tier;
    if (hasValue(tier)) {
      badges.append(
        createElement(
          "span",
          "candidate-signals-dossier-tier",
          String(tier).toUpperCase()
        )
      );
    }
    if (badges.children.length) copy.append(badges);
    identity.append(copy);

    const campaign = candidate.campaign_attention;
    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;
    const poll = candidate.polling;
    const pollReported = poll?.evidence_state === "reported";
    const campaignReported = hasAttentionObservation(campaign);
    const raceAttention = isRaceAttentionEvidence(campaign);
    const hypothesisCount = pollReported && hasValue(poll.hypothesis_count)
      ? numberText(poll.hypothesis_count)
      : null;
    const period = raceAttention
      ? metadata?.activeFieldVisibility?.race_attention?.current_period
      : metadata?.visibility?.current_period;
    const periodText = period
      ? formatDateRange(period.start_date, period.end_date)
      : null;
    const newestDate = (
      latest?.newest_review_date || archive?.newest_review_date
    );

    const metrics = createElement(
      "div",
      "candidate-signals-dossier-metrics"
    );
    metrics.append(
      dossierMetric(
        "POLL EVIDENCE",
        pollValue(candidate),
        pollReported
          ? [
            rangeText(poll.range_min, poll.range_max),
            hypothesisCount
              ? `${hypothesisCount} hypotheses`
              : null
          ]
          : ["Not tested in featured package"]
      ),
      dossierMetric(
        raceAttention ? "RACE ATTENTION" : "CAMPAIGN ATTENTION",
        campaignReported ? percentageText(campaign.share, true) : MISSING,
        campaignReported
          ? raceAttention
            ? [
              counted(campaign.exposure_count, "exposure"),
              counted(campaign.story_count, "story"),
              counted(campaign.publisher_count, "publisher")
            ]
            : [
              counted(campaign.record_count, "record"),
              counted(campaign.publisher_count, "publisher")
            ]
          : ["No current evidence"]
      ),
      dossierMetric(
        "SCRUTINY · 14 DAYS",
        latest
          ? `${numberText(latest.about_count)} about · ${numberText(
            latest.by_count
          )} by`
          : MISSING,
        latest
          ? [
            counted(latest.review_count, "review"),
            `Latest review · ${formatDisplayDate(newestDate)}`
          ]
          : ["No current evidence"],
        "is-composite"
      ),
      dossierMetric(
        raceAttention ? "RACE EXPOSURES" : "ACTIVE DAYS",
        campaignReported && hasValue(
          raceAttention
            ? campaign.exposure_count
            : campaign.active_day_count
        )
          ? numberText(
            raceAttention
              ? campaign.exposure_count
              : campaign.active_day_count
          )
          : MISSING,
        campaignReported
          ? raceAttention
            ? [
              counted(campaign.story_count, "story"),
              "Current published period",
              periodText
            ]
            : ["Current published period", periodText]
          : ["No current evidence", periodText]
      )
    );

    const grid = createElement("div", "candidate-signals-dossier-grid");
    grid.append(
      dossierVisibilityPanel(candidate),
      evidenceStructurePanel(candidate),
      scrutinyOverviewPanel(candidate),
      dossierLatestDevelopment(candidate),
      compactEvidenceDetails(candidate, metadata)
    );

    body.append(identity, metrics, grid);
    section.append(header, body);
    return section;
  }

  function selectedPollScore(candidate) {
    const polling = candidate?.polling;
    if (
      polling?.evidence_state !== "reported" ||
      !hasValue(polling.selected_hypothesis_score)
    ) {
      return null;
    }

    const score = Number(polling.selected_hypothesis_score);
    return Number.isFinite(score) ? score : null;
  }

  function pollOrderGroup(candidate) {
    if (selectedPollScore(candidate) !== null) return 0;
    return candidate?.polling?.evidence_state === "reported" ? 1 : 2;
  }

  function orderWorkspaceCandidates(candidates) {
    const ordered = [];

    candidates.forEach(candidate => {
      const group = pollOrderGroup(candidate);
      const score = selectedPollScore(candidate);
      const insertion = ordered.findIndex(existing => {
        const existingGroup = pollOrderGroup(existing);

        if (group !== existingGroup) return group < existingGroup;
        if (group !== 0) return false;

        const existingScore = selectedPollScore(existing);
        return existingScore !== null && score > existingScore;
      });

      if (insertion === -1) {
        ordered.push(candidate);
      } else {
        ordered.splice(insertion, 0, candidate);
      }
    });

    return ordered;
  }

  function activeWorkspaceCandidates(candidates, metadata) {
    const field = metadata?.activeMonitoringField ||
      metadata?.presidentialField;
    const activeIds = [
      ...(Array.isArray(field?.main) ? field.main : []),
      ...(Array.isArray(field?.secondary) ? field.secondary : [])
    ];
    const active = new Set(activeIds);
    const hasPresidentialField = field &&
      Array.isArray(field.main) &&
      Array.isArray(field.secondary);
    const visible = hasPresidentialField
      ? candidates.filter(candidate => active.has(
        candidate.candidate_id
      ))
      : candidates;

    return orderWorkspaceCandidates(visible);
  }

  function render(mount, state, options = {}) {
    if (!mount || typeof mount.replaceChildren !== "function") return null;

    const status = stateNames.has(state?.status)
      ? state.status
      : "unavailable";
    mount.setAttribute("data-candidate-signals-state", status);
    mount.replaceChildren();

    if (status === "loading") {
      mount.append(statePresentation("Loading candidate evidence…", true));
      return null;
    }
    if (status === "empty") {
      mount.append(
        statePresentation("No candidate evidence is currently published.")
      );
      return null;
    }
    if (status === "unavailable") {
      mount.append(
        statePresentation("Candidate evidence is temporarily unavailable.")
      );
      return null;
    }

    const publishedCandidates = Array.isArray(state.candidates)
      ? state.candidates
      : [];
    const candidates = activeWorkspaceCandidates(
      publishedCandidates,
      state.metadata || {}
    );
    if (!candidates.length) {
      mount.setAttribute("data-candidate-signals-state", "empty");
      mount.append(
        statePresentation("No candidate evidence is currently published.")
      );
      return null;
    }

    const selected = candidates.some(
      candidate => candidate.candidate_id === options.selectedCandidateId
    )
      ? options.selectedCandidateId
      : candidates[0].candidate_id;

    const chooseCandidate = (candidateId, restoreFocus) => {
      if (candidateId === selected) {
        if (restoreFocus) {
          const current = [...mount.querySelectorAll(
            ".candidate-signals-candidate-button"
          )].find(button =>
            button.dataset.candidateSignalsCandidate === candidateId
          );
          current?.focus();
        }
        return;
      }

      if (typeof options.onSelect === "function") {
        options.onSelect(candidateId);
      } else {
        render(mount, state, {
          selectedCandidateId: candidateId,
          resolvePortrait: options.resolvePortrait
        });
      }

      if (restoreFocus) {
        const current = [...mount.querySelectorAll(
          ".candidate-signals-candidate-button"
        )].find(button =>
          button.dataset.candidateSignalsCandidate === candidateId
        );
        current?.focus();
      }
    };

    const selectedCandidate = candidates.find(
      candidate => candidate.candidate_id === selected
    );
    const workspace = createElement("div", "candidate-signals-workspace");
    workspace.append(
      candidateMonitor(candidates, selected, options, chooseCandidate),
      selectedAnalysis(
        selectedCandidate,
        state.metadata || {},
        options.candidateAttention
      ),
      candidateDossier(selectedCandidate, state.metadata || {}, options)
    );
    mount.append(workspace);
    return selected;
  }

  window.France2027CandidateSignalsWorkspace = Object.freeze({
    render
  });
})();
