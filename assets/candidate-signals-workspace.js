(() => {
  "use strict";


  const translate = (key, fallback, parameters) => {
    const localizer = globalThis.FR27I18N;

    if (localizer && typeof localizer.t === "function") {
      return localizer.t(key, parameters, fallback);
    }

    const values = parameters || {};
    const pluralized = String(fallback).replace(
      /\{([A-Za-z0-9_]+),\s*plural,\s*one\s*\{([^{}]*)\}\s*other\s*\{([^{}]*)\}\s*\}/g,
      (_match, name, one, other) =>
        new Intl.PluralRules("en-GB").select(Number(values[name])) === "one"
          ? one
          : other
    );
    return pluralized.replace(
      /\{([A-Za-z0-9_]+)\}/g,
      (match, name) => Object.prototype.hasOwnProperty.call(values, name)
        ? String(values[name])
        : match
    );
  };

  const localeTag = () => globalThis.FR27I18N?.localeTag || "en-GB";

  const formatLocaleNumber = (value, options = {}) => {
    const localizer = globalThis.FR27I18N;
    return localizer && typeof localizer.formatNumber === "function"
      ? localizer.formatNumber(value, options)
      : new Intl.NumberFormat(localeTag(), options).format(value);
  };

  const MISSING = translate("candidate.not_published", "Not published");
  const NOT_TESTED = translate("candidate.not_tested", "Not tested");
  const SCRUTINY_ABOUT_SEMANTICS =
    translate(
      "candidate.scrutiny.about_semantics",
      "ABOUT — candidate mentioned in a claim attributed to someone else."
    );
  const SCRUTINY_BY_SEMANTICS =
    translate(
      "candidate.scrutiny.by_semantics",
      "BY — candidate is the recorded claimant."
    );
  const CAMPAIGN_ATTENTION_SEMANTICS =
    translate(
      "candidate.campaign_attention_semantics",
      "Share of active-field-linked campaign/election records in the current period. A record may mention more than one candidate."
    );
  const RACE_RECORDS_SEMANTICS =
    translate(
      "candidate.race_records_semantics",
      "Candidate-linked campaign/election records in the current period."
    );
  const LATEST_DEVELOPMENT_EXPLANATION =
    translate(
      "candidate.latest_development_explanation",
      "Newest campaign/election record with this candidate matched in the headline."
    );
  const POLICY_AGENDA_SEMANTICS =
    "Candidate × policy-issue coverage associations derived from the published multi-label Policy Issues layer over the 30-day window. These measure media coverage association, not candidate priorities, positions, issue ownership, ideology, or policy support.";
  const CAMPAIGN_AGENDA_SEMANTICS =
    "Candidate-linked campaign/election records classified into the published Campaign Agenda themes over the 30-day window. These describe campaign and race-process coverage, not substantive policy priorities or positions.";
  const AGENDA_PROFILE_LABELS = Object.freeze({
    economy_public_finances: "Economy / finances",
    work_purchasing_power_pensions: "Work / purchasing power",
    immigration_identity_secularism: "Immigration / identity",
    security_justice: "Security / justice",
    health_education_public_services: "Health / education",
    climate_energy_agriculture: "Climate / energy",
    europe_defence_foreign_affairs: "Europe / defence",
    institutions_democracy_territories: "Institutions / democracy",
    legal_eligibility: "Legal / eligibility",
    selection_strategy: "Primaries / strategy",
    candidacies_endorsements: "Candidacies / endorsements",
    rules_calendar: "Rules / calendar",
    positioning_integrity: "Positioning / image",
    polls_race: "Polling / race"
  });
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

  function semanticMetadata(node, title, ariaLabel = title) {
    node.setAttribute("aria-label", ariaLabel);
    return node;
  }

  function explanatoryMetadata(node, title, ariaLabel = title) {
    semanticMetadata(node, title, ariaLabel);
    node.setAttribute("data-fr27-tooltip", title);
    node.setAttribute("data-fr27-tooltip-affordance", "term");
    node.setAttribute("tabindex", "0");
    return node;
  }

  function hasValue(value) {
    return value !== null && value !== undefined && value !== "";
  }

  function numberText(value) {
    return hasValue(value) && Number.isFinite(Number(value))
      ? formatLocaleNumber(Number(value), { maximumFractionDigits: 3 })
      : MISSING;
  }

  function groupedNumberText(value) {
    if (!hasValue(value) || !Number.isFinite(Number(value))) return MISSING;
    return formatLocaleNumber(Math.trunc(Number(value)), {
      maximumFractionDigits: 0
    });
  }

  function percentageText(value, ratio = false) {
    if (!hasValue(value) || !Number.isFinite(Number(value))) return MISSING;
    const amount = ratio ? Number(value) : Number(value) / 100;
    return formatLocaleNumber(amount, {
      style: "percent",
      maximumFractionDigits: 3
    });
  }

  function compactPercentageText(value, ratio = false) {
    if (!hasValue(value) || !Number.isFinite(Number(value))) return MISSING;
    const amount = ratio ? Number(value) : Number(value) / 100;
    return formatLocaleNumber(amount, {
      style: "percent",
      maximumFractionDigits: 1
    });
  }

  function rangeText(minimum, maximum) {
    if (!hasValue(minimum) || !hasValue(maximum)) return MISSING;
    if (Number(minimum) === Number(maximum)) return percentageText(minimum);
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

    const dateText = new Intl.DateTimeFormat(localeTag(), {
      day: "numeric",
      month: "short",
      year: "numeric",
      timeZone: "UTC"
    }).format(date);

    if (!includeTime) return dateText;

    const timeText = new Intl.DateTimeFormat(localeTag(), {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "UTC"
    }).format(date);

    return `${dateText} · ${timeText} UTC`;
  }

  function formatCompactDayMonth(value) {
    if (!hasValue(value)) return MISSING;
    const date = new Date(`${value}T00:00:00Z`);
    if (!Number.isFinite(date.getTime())) return String(value);

    const parts = new Intl.DateTimeFormat(localeTag(), {
      day: "2-digit",
      month: "short",
      timeZone: "UTC"
    }).formatToParts(date);
    const day = parts.find(part => part.type === "day")?.value;
    const month = parts.find(part => part.type === "month")?.value;
    return day && month
      ? `${day} ${(localeTag().toLowerCase().startsWith("fr") ? month : month.slice(0, 3)).toLocaleUpperCase(localeTag())}`
      : String(value);
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
      const monthYear = new Intl.DateTimeFormat(localeTag(), {
        month: "short",
        year: "numeric",
        timeZone: "UTC"
      }).format(end);

      const startDay = new Intl.DateTimeFormat(localeTag(), {
        day: "numeric",
        timeZone: "UTC"
      }).format(start);
      const endDay = new Intl.DateTimeFormat(localeTag(), {
        day: "numeric",
        timeZone: "UTC"
      }).format(end);
      return `${startDay}–${endDay} ${monthYear}`;
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

  function candidacyStatusLabel(value) {
    return translate(
      `candidate.status.${String(value || "").toLowerCase()}`,
      humanizeStatus(value)
    );
  }

  function candidacyTierLabel(value) {
    return translate(
      `candidate.tier.${String(value || "").toLowerCase()}`,
      humanizeStatus(value)
    );
  }

  function counted(value, kind) {
    if (!hasValue(value)) return MISSING;
    const number = Number(value);
    if (!Number.isFinite(number)) return MISSING;
    const fallbacks = {
      record: "{count} {count, plural, one {record} other {records}}",
      publisher: "{count} {count, plural, one {publisher} other {publishers}}",
      active_day: "{count} {count, plural, one {active day} other {active days}}",
      review: "{count} {count, plural, one {review} other {reviews}}"
    };
    return translate(
      `candidate.count.${kind}`,
      fallbacks[kind] || "{count}",
      { count: numberText(number) }
    );
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

  function evidenceStateGroup(title, message) {
    const group = createElement(
      "div",
      "candidate-signals-evidence-group"
    );
    group.append(
      createElement(
        "h4",
        "candidate-signals-evidence-group-title",
        title
      ),
      createElement(
        "p",
        "candidate-signals-development-empty",
        message
      )
    );
    return group;
  }

  function visibilityLines(candidate) {
    const campaign = candidate.campaign_attention;
    const general = candidate.general_visibility;
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

  function skeletonPresentation(pattern, label) {
    if (window.FR27UI?.skeletonElement) {
      return window.FR27UI.skeletonElement(pattern, label);
    }
    const fallback = statePresentation("—", true);
    fallback.setAttribute("aria-label", label);
    return fallback;
  }

  function candidateSecondary(candidate) {
    const campaign = candidate.campaign_attention;
    const general = candidate.general_visibility;
    const parts = [];

    if (campaign?.evidence_state === "reported") {
      parts.push(
        translate(
          "candidate.campaign_election_count",
          "Campaign / election {count}",
          { count: numberText(campaign.record_count) }
        )
      );
    }

    if (general?.evidence_state === "reported") {
      parts.push(
        translate(
          "candidate.general_count",
          "General {count}",
          { count: numberText(general.record_count) }
        )
      );
    }

    return parts.length
      ? parts.join(" · ")
      : translate(
        "candidate.no_current_coverage_evidence",
        "No current coverage evidence"
      );
  }

  function candidateFact(label, value, className = "", semantics = null) {
    const fact = createElement(
      "span",
      `candidate-signals-candidate-fact${className ? ` ${className}` : ""}`
    );
    const labelNode = createElement(
      "span",
      "candidate-signals-candidate-fact-label",
      label
    );
    if (semantics) {
      semanticMetadata(labelNode, semantics);
    }
    fact.append(
      labelNode,
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
      translate("candidate.search_candidate_label", "Search candidate")
    );
    label.setAttribute("for", "candidate-signals-search");

    const input = createElement("input", "candidate-signals-search-input");
    input.id = "candidate-signals-search";
    input.type = "search";
    input.placeholder = translate(
      "candidate.search_candidate",
      "Search candidate…"
    );
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
      translate(
        "candidate.show_main_candidates_only",
        "Show main candidates only"
      )
    );
    filterButton.dataset.fr27Tooltip = translate(
      "candidate.show_main_candidates_only",
      "Show main candidates only"
    );

    const filterGlyph = createElement(
      "span",
      "candidate-signals-filter-glyph"
    );
    filterGlyph.setAttribute("aria-hidden", "true");
    filterButton.append(filterGlyph);

    tools.append(label, input, filterButton);

    const list = createElement("div", "candidate-signals-monitor-list");
    list.id = "candidate-signals-monitor-list";
    list.setAttribute(
      "aria-label",
      translate("candidate.published_candidates", "Published candidates")
    );

    const noMatches = createElement(
      "p",
      "candidate-signals-monitor-empty",
      translate("candidate.no_matching_candidates", "No matching candidates.")
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
            candidacyTierLabel(tier).toLocaleUpperCase(localeTag())
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
      const latest = candidate.scrutiny?.latest_14_days;
      const campaignReported =
        campaign?.evidence_state === "reported";
      const evidence = createElement(
        "span",
        "candidate-signals-candidate-evidence"
      );

      if (campaignReported) {
        evidence.append(
          candidateFact(
            translate("candidate.campaign_attention", "CAMPAIGN ATTENTION"),
            percentageText(campaign.share, true),
            "candidate-signals-candidate-attention",
            CAMPAIGN_ATTENTION_SEMANTICS
          ),
          candidateFact(
            translate("candidate.race_records", "RACE RECORDS"),
            numberText(campaign.record_count),
            "candidate-signals-candidate-records",
            RACE_RECORDS_SEMANTICS
          )
        );
      }

      if (latest) {
        evidence.append(
          candidateFact(
            translate(
              "candidate.scrutiny_monitor_14_days",
              "Scrutiny\n14 days"
            ),
            translate(
              "candidate.scrutiny_relationship_counts",
              "{about} about · {by} by",
              {
                about: numberText(latest.about_count),
                by: numberText(latest.by_count)
              }
            ),
            "candidate-signals-candidate-scrutiny"
          )
        );
      }

      button.append(top);
      if (evidence.children.length) {
        button.append(evidence);
      }
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
        ? translate("candidate.show_all_candidates", "Show all candidates")
        : translate(
          "candidate.show_main_candidates_only",
          "Show main candidates only"
        );

      filterButton.setAttribute("aria-label", description);
      filterButton.dataset.fr27Tooltip = description;

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
        translate("candidate.candidacy_evidence", "CANDIDACY EVIDENCE")
      )
    );

    const candidacy = candidate.candidacy;
    if (!candidacy) {
      section.append(
        createElement(
          "p",
          "candidate-signals-development-empty",
          translate(
            "candidate.no_candidacy_evidence_is_currently_published",
            "No candidacy evidence is currently published."
          )
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
        candidacyStatusLabel(candidacy.status)
      )
    );

    if (hasValue(candidacy.display_tier)) {
      statusRow.append(
        createElement(
          "span",
          `candidate-signals-candidacy-tier is-${String(
            candidacy.display_tier
          ).toLowerCase()}`,
          candidacyTierLabel(candidacy.display_tier)
            .toLocaleUpperCase(localeTag())
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
        translate("candidate.source", "Source")
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
        translate("candidate.view_candidacy_source", "View candidacy source →")
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
          translate(
            "candidate.no_source_linked_development_is_currently_published",
            "No source-linked development is currently published."
          )
        )
      ];
    }

    const content = [
      createElement(
        detailed ? "h4" : "strong",
        "candidate-signals-development-headline",
        development.headline || MISSING
      ),
      evidenceLine(translate("candidate.source", "Source"), development.publisher),
      evidenceLine(
        translate("candidate.published", "Published"),
        formatDisplayDate(development.published_at, true)
      )
    ];
    const href = safeUrl(development.url);
    if (href) {
      const link = createElement(
        "a",
        "candidate-signals-source-link",
        translate("candidate.open_source", "Open source ↗")
      );
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      content.push(link);
    } else {
      content.push(
        evidenceLine(translate("candidate.source_link", "Source link"), MISSING)
      );
    }
    return content;
  }

  function analysisLatestDevelopment(candidate) {
    const section = createElement(
      "section",
      "candidate-signals-latest-development"
    );
    section.append(
      explanatoryMetadata(
        createElement(
          "h3",
          "candidate-signals-subsection-title",
          translate("candidate.latest_development", "LATEST DEVELOPMENT")
        ),
        LATEST_DEVELOPMENT_EXPLANATION,
        translate(
          "candidate.latest_development_aria",
          "LATEST DEVELOPMENT — {explanation}",
          { explanation: LATEST_DEVELOPMENT_EXPLANATION }
        )
      )
    );

    const development = candidate.latest_development;
    if (!development || !hasValue(development.headline)) {
      section.append(
        createElement(
          "p",
          "candidate-signals-development-empty",
          translate(
            "candidate.no_source_linked_development_is_currently_published",
            "No source-linked development is currently published."
          )
        )
      );
      return section;
    }

    if (hasValue(development.coverage_scope)) {
      section.append(
        createElement(
          "span",
          "candidate-signals-development-scope",
          translate(
            `candidate.scope.${String(development.coverage_scope).toLowerCase()}`,
            String(development.coverage_scope)
          ).toLocaleUpperCase(localeTag())
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
        translate("candidate.open_latest_source", "Open latest source →")
      );
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      section.append(link);
    } else {
      section.append(
        evidenceLine(translate("candidate.source_link", "Source link"), MISSING)
      );
    }

    return section;
  }

  function dossierLatestDevelopment(candidate) {
    const section = createElement(
      "section",
      "candidate-signals-dossier-card candidate-signals-dossier-development"
    );
    section.append(
      explanatoryMetadata(
        createElement(
          "h3",
          "candidate-signals-dossier-card-title",
          translate("candidate.latest_development", "LATEST DEVELOPMENT")
        ),
        LATEST_DEVELOPMENT_EXPLANATION,
        translate(
          "candidate.latest_development_aria",
          "LATEST DEVELOPMENT — {explanation}",
          { explanation: LATEST_DEVELOPMENT_EXPLANATION }
        )
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
    const counts = (
      candidate.campaign_attention?.evidence_state === "reported"
    )
      ? candidate.campaign_attention.scope_counts
      : null;
    const values = ["campaign", "election"].map(key => {
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

  function summaryCard(title, className = "", tagName = "article") {
    const card = createElement(
      tagName,
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

  function agendaSummaryCard(
    profile,
    {
      title,
      countField,
      metadata,
      emptyMessage
    }
  ) {
    const card = summaryCard(
      title,
      "candidate-signals-agenda-summary"
    );

    if (!profile) {
      card.setAttribute(
        "aria-label",
        `${title} — ${emptyMessage}`
      );
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state candidate-signals-agenda-empty",
          emptyMessage
        )
      );
      return card;
    }

    const titleNode = card.querySelector(
      ".candidate-signals-analysis-card-title"
    );

    if (titleNode) {
      const heading = createElement(
        "div",
        "candidate-signals-agenda-head"
      );
      const info = createElement(
        "button",
        "candidate-signals-agenda-info",
        "i"
      );
      info.setAttribute("type", "button");

      explanatoryMetadata(
        info,
        metadata,
        `${title} information. ${metadata}`
      );

      titleNode.remove();
      heading.append(titleNode, info);
      card.append(heading);
    }

    card.setAttribute(
      "aria-label",
      `${title} — ${metadata}`
    );

    const ranked = [];

    for (const topic of profile.topics) {
      if (
        !hasValue(topic[countField]) ||
        Number(topic[countField]) <= 0
      ) {
        continue;
      }

      let inserted = false;

      for (let index = 0; index < ranked.length; index += 1) {
        if (
          Number(topic[countField]) >
          Number(ranked[index][countField])
        ) {
          ranked.splice(index, 0, topic);
          inserted = true;
          break;
        }
      }

      if (!inserted) {
        ranked.push(topic);
      }

      if (ranked.length > 4) {
        ranked.pop();
      }
    }

    if (!ranked.length) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state candidate-signals-agenda-empty",
          emptyMessage
        )
      );
      return card;
    }

    const list = createElement(
      "div",
      "candidate-signals-agenda-topics"
    );

    for (const topic of ranked) {
      const row = createElement(
        "div",
        "candidate-signals-agenda-topic"
      );
      const line = createElement(
        "div",
        "candidate-signals-agenda-topic-line"
      );
      const label = createElement(
        "span",
        "candidate-signals-agenda-topic-label",
        localeTag().toLowerCase().startsWith("fr")
          ? translate(
              `agenda_topic_short.${topic.id}`,
              AGENDA_PROFILE_LABELS[topic.id] || topic.label
            )
          : AGENDA_PROFILE_LABELS[topic.id] || topic.label
      );
      const share = createElement(
        "strong",
        "candidate-signals-agenda-topic-share",
        compactPercentageText(topic.share, true)
      );
      const track = createElement(
        "span",
        "candidate-signals-agenda-topic-track"
      );
      const fill = createElement(
        "span",
        "candidate-signals-agenda-topic-fill"
      );

      const width = percentageNumber(topic.share, true);
      fill.style.width = `${width === null ? 0 : width}%`;
      track.append(fill);
      line.append(label, share);
      row.append(line, track);
      list.append(row);
    }

    card.append(list);
    return card;
  }

  function currentAgendaSummaryCard(candidate) {
    const profile = candidate.agenda_profile;
    if (!profile) return null;

    const mode = profile.profile_mode === "policy"
      ? "POLICY"
      : "CAMPAIGN";
    const semantics = profile.profile_mode === "policy"
      ? POLICY_AGENDA_SEMANTICS
      : CAMPAIGN_AGENDA_SEMANTICS;
    const period = formatDateRange(
      profile.period_start,
      profile.period_end
    );
    const metadata = `${mode} · ${profile.window_days}D · ${
      numberText(profile.association_count)
    } LINKS · ${period} — ${semantics}`;

    return agendaSummaryCard(
      profile,
      {
        title: translate(
          "candidate.agenda_profile.current_title",
          "AGENDA PROFILE · 30D"
        ),
        countField: "association_count",
        metadata,
        emptyMessage:
          "No classified topic coverage in the current 30-day window."
      }
    );
  }

  function historicalAgendaSummaryCard(
    candidate,
    historyState
  ) {
    const candidates = historyState?.status === "ready"
      ? historyState.payload?.candidates
      : null;
    const record = Array.isArray(candidates)
      ? candidates.find(
        item => item.candidate_id === candidate.candidate_id
      )
      : null;
    const title = record
      ? translate(
          "candidate.agenda_profile.since_title",
          "AGENDA PROFILE · SINCE {date}",
          { date: formatCompactDayMonth(record.tracking_start) }
        )
      : translate(
          "candidate.agenda_profile.since_tracking",
          "AGENDA PROFILE · SINCE TRACKING"
        );
    const unavailableMessage =
      "Cumulative Agenda Profile is unavailable for this candidate.";

    if (!record?.cumulative_profile) {
      return agendaSummaryCard(
        null,
        {
          title,
          countField: "count",
          metadata: "",
          emptyMessage: unavailableMessage
        }
      );
    }

    const profile = record.cumulative_profile;
    const mode = profile.profile_mode === "policy"
      ? "POLICY"
      : "CAMPAIGN";
    const period = formatDateRange(
      profile.period_start,
      profile.period_end
    );
    const metadata = `${mode} · ${
      numberText(profile.association_count)
    } LINKS · ${period} — Cumulative Agenda Profile since ${
      formatDisplayDate(record.tracking_start)
    }, through ${formatDisplayDate(profile.period_end)}, based on accepted News Wire evidence. Policy mode is used when at least 3 substantive policy topics are observed; otherwise campaign-topic fallback is used. Displays the four leading non-zero topics. Coverage/topic evidence, not candidate support or sentiment.`;

    return agendaSummaryCard(
      profile,
      {
        title,
        countField: "count",
        metadata,
        emptyMessage:
          "No classified topic coverage since tracking began."
      }
    );
  }


  function summaryMeta(label, value, className = "") {
    const row = createElement(
      "div",
      `candidate-signals-summary-meta${className ? ` ${className}` : ""}`
    );
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
      translate("candidate.poll_evidence", "POLL EVIDENCE"),
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

    if (reported) {
      const pollster = pollPackage?.pollster || MISSING;
      const fieldwork = formatDateRange(
        pollPackage?.fieldwork_start,
        pollPackage?.fieldwork_end
      );
      const hypotheses = hasValue(poll?.hypothesis_count)
        ? translate(
          "candidate.count.hypothesis",
          "{count} {count, plural, one {hypothesis} other {hypotheses}}",
          { count: numberText(poll.hypothesis_count) }
        )
        : MISSING;
      const sample = hasValue(pollPackage?.sample_size)
        ? `N=${groupedNumberText(pollPackage.sample_size)}`
        : MISSING;
      const publishedRange = hasRange
        ? rangeText(poll.range_min, poll.range_max)
        : MISSING;

      const infoText = translate(
        "candidate.poll_evidence_details",
        "Pollster: {pollster}. Fieldwork: {fieldwork}. Sample: {sample}. Package: {hypotheses}. Published candidate range: {range}.",
        { pollster, fieldwork, sample, hypotheses, range: publishedRange }
      );

      const info = createElement(
        "button",
        "candidate-signals-poll-evidence-info",
        "i"
      );
      info.setAttribute("type", "button");

      explanatoryMetadata(
        info,
        infoText,
        translate(
          "candidate.poll_evidence_information",
          "Poll evidence information. {details}",
          { details: infoText }
        )
      );

      const title = card.querySelector(
        ".candidate-signals-analysis-card-title"
      );

      if (title) {
        const heading = createElement(
          "div",
          "candidate-signals-poll-evidence-head"
        );
        title.remove();
        heading.append(title, info);
        card.append(heading);
      }
    }

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
          ? translate(
            "candidate.published_range_value",
            "Published range {range}",
            { range: rangeText(minimum, maximum) }
          )
          : translate(
            "candidate.published_range_selected_estimate",
            "Published range {range}; selected estimate {estimate}",
            {
              range: rangeText(minimum, maximum),
              estimate: percentageText(selected)
            }
          )
      );
      gauge.append(
        createElement(
          "span",
          "candidate-signals-poll-gauge-kicker",
          translate("candidate.published_range_heading", "PUBLISHED RANGE")
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
          translate(
            "candidate.no_accepted_first_round_test_in_the_current_polling_window",
            "No accepted first-round test in the current polling window."
          )
        )
      );
    }

    return card;
  }

  function pollHistoryForDisplay(source) {
    if (!source || typeof source !== "object") return null;

    if (
      source.evidence_state === "not_observed" &&
      source.observation_count === 0 &&
      source.period_start === null &&
      source.period_end === null &&
      Array.isArray(source.observations) &&
      source.observations.length === 0
    ) {
      return source;
    }

    if (
      source.evidence_state !== "reported" ||
      !Number.isInteger(source.observation_count) ||
      source.observation_count <= 0 ||
      !Array.isArray(source.observations) ||
      source.observation_count !== source.observations.length ||
      !hasValue(source.period_start) ||
      !hasValue(source.period_end)
    ) {
      return null;
    }

    for (const observation of source.observations) {
      if (!observation || typeof observation !== "object") return null;

      const minimum = Number(observation.range_min);
      const maximum = Number(observation.range_max);
      const selected = observation.selected_score === null
        ? null
        : Number(observation.selected_score);

      if (
        !hasValue(observation.pollster) ||
        !hasValue(observation.fieldwork_start) ||
        !hasValue(observation.fieldwork_end) ||
        !Number.isInteger(observation.hypothesis_count) ||
        observation.hypothesis_count <= 0 ||
        !hasValue(observation.range_min) ||
        !hasValue(observation.range_max) ||
        !Number.isFinite(minimum) ||
        !Number.isFinite(maximum) ||
        minimum < 0 ||
        minimum > maximum ||
        (
          selected !== null &&
          (
            !Number.isFinite(selected) ||
            selected < minimum ||
            selected > maximum
          )
        )
      ) {
        return null;
      }
    }

    return source;
  }

  function pollHistoryObservationLabel(observation) {
    const pollster = observation.pollster;
    const fieldwork = formatDateRange(
      observation.fieldwork_start,
      observation.fieldwork_end
    );
    const hypotheses = `${numberText(
      observation.hypothesis_count
    )} ${
      observation.hypothesis_count === 1
        ? translate("candidate.hypothesis", "hypothesis")
        : translate("candidate.hypotheses", "hypotheses")
    }`;
    const publishedRange = rangeText(
      observation.range_min,
      observation.range_max
    );

    if (observation.selected_score !== null) {
      return translate(
        "candidate.poll_history_exact_observation",
        "{pollster}, {fieldwork}: exact selected-hypothesis score {score}; package range {range}; {hypotheses}.",
        {
          pollster,
          fieldwork,
          score: percentageText(observation.selected_score),
          range: publishedRange,
          hypotheses
        }
      );
    }

    return translate(
      "candidate.poll_history_range_observation",
      "{pollster}, {fieldwork}: published package range {range}; no selected-hypothesis score; {hypotheses}.",
      { pollster, fieldwork, range: publishedRange, hypotheses }
    );
  }

  function pollHistoryChart(history, candidate) {
    const observations = history.observations;
    const values = observations.flatMap(observation => [
      Number(observation.range_min),
      Number(observation.range_max)
    ]);
    const observedMinimum = Math.min(...values);
    const observedMaximum = Math.max(...values);
    const scaleMinimum = Math.max(0, Math.floor(observedMinimum - 2));
    const scaleMaximum = Math.max(
      scaleMinimum + 1,
      Math.ceil(observedMaximum + 2)
    );
    const width = 260;
    const height = 74;
    const margin = { top: 5, right: 4, bottom: 2, left: 4 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const xFor = index => margin.left + (
      observations.length === 1
        ? plotWidth / 2
        : (index / (observations.length - 1)) * plotWidth
    );
    const yFor = value => margin.top + (
      1 - (
        (Number(value) - scaleMinimum) /
        (scaleMaximum - scaleMinimum)
      )
    ) * plotHeight;
    const exactCount = observations.filter(
      observation => observation.selected_score !== null
    ).length;
    const rangeOnlyCount = observations.length - exactCount;

    const svg = wikipediaSvgElement(
      "svg",
      "candidate-signals-poll-history-chart"
    );
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      translate(
        "candidate.poll_history_chart_aria",
        "{count} chronological package-level poll observations for {candidate}: {exact} exact selected scores and {ranges} published ranges without a selected score. Points are discrete observations and bars are published ranges; no averaging or interpolation.",
        {
          count: numberText(history.observation_count),
          candidate: candidate.candidate_name,
          exact: numberText(exactCount),
          ranges: numberText(rangeOnlyCount)
        }
      )
    );

     observations.forEach((observation, index) => {
      const x = xFor(index);
      const minimumY = yFor(observation.range_min);
      const maximumY = yFor(observation.range_max);
      const label = pollHistoryObservationLabel(observation);

      if (observation.selected_score === null) {
        const range = wikipediaSvgElement(
          "g",
          "candidate-signals-poll-history-range"
        );
        range.setAttribute("aria-label", label);
        range.setAttribute("data-fr27-tooltip", label);

        const stem = wikipediaSvgElement("line");
        stem.setAttribute("x1", x);
        stem.setAttribute("x2", x);
        stem.setAttribute("y1", maximumY);
        stem.setAttribute("y2", minimumY);

        const capMinimum = wikipediaSvgElement("line");
        capMinimum.setAttribute("x1", x - 2.5);
        capMinimum.setAttribute("x2", x + 2.5);
        capMinimum.setAttribute("y1", minimumY);
        capMinimum.setAttribute("y2", minimumY);

        const capMaximum = wikipediaSvgElement("line");
        capMaximum.setAttribute("x1", x - 2.5);
        capMaximum.setAttribute("x2", x + 2.5);
        capMaximum.setAttribute("y1", maximumY);
        capMaximum.setAttribute("y2", maximumY);

        range.append(stem, capMinimum, capMaximum);
        svg.append(range);
        return;
      }

      if (Number(observation.range_min) !== Number(observation.range_max)) {
        const contextRange = wikipediaSvgElement(
          "line",
          "candidate-signals-poll-history-context-range"
        );
        contextRange.setAttribute("x1", x);
        contextRange.setAttribute("x2", x);
        contextRange.setAttribute("y1", maximumY);
        contextRange.setAttribute("y2", minimumY);
        contextRange.setAttribute("aria-hidden", "true");
        svg.append(contextRange);
      }

      const point = wikipediaSvgElement(
        "circle",
        "candidate-signals-poll-history-point"
      );
      point.setAttribute("cx", x);
      point.setAttribute("cy", yFor(observation.selected_score));
      point.setAttribute("r", observations.length >= 30 ? 1.8 : 2.15);
      point.setAttribute("aria-label", label);
      point.setAttribute("data-fr27-tooltip", label);
      svg.append(point);
    });

    return svg;
  }

  function pollHistoryCardHeading(card, history) {
    const title = card.querySelector(
      ".candidate-signals-analysis-card-title"
    );
    const heading = createElement(
      "div",
      "candidate-signals-poll-history-head"
    );
    const controls = createElement(
      "div",
      "candidate-signals-poll-history-head-controls"
    );
    const reported = history?.evidence_state === "reported";
    const notObserved = history?.evidence_state === "not_observed";
    const count = reported || notObserved
      ? numberText(history.observation_count)
      : null;
    const period = reported
      ? formatDateRange(history.period_start, history.period_end)
      : notObserved
        ? translate("candidate.no_covered_period", "No covered period")
        : translate("candidate.unavailable", "Unavailable");
    const infoText = translate(
      "candidate.poll_history_details",
      "Observation count: {count}. Covered period: {period}. Points = exact reported scores. Bars = published ranges. Observations are equally spaced in chronological order; horizontal spacing does not represent elapsed time. No averaging, smoothing or interpolation.",
      {
        count: count === null
          ? translate("candidate.unavailable", "unavailable")
          : count,
        period
      }
    );
    const info = createElement(
      "button",
      "candidate-signals-poll-history-info",
      "i"
    );

    info.setAttribute("type", "button");
    explanatoryMetadata(
      info,
      infoText,
      translate(
        "candidate.poll_history_information",
        "Poll history information. {details}",
        { details: infoText }
      )
    );

    if (count !== null) {
      controls.append(
        createElement(
          "span",
          "candidate-signals-poll-history-count",
          translate("candidate.observation_abbreviation", "{count} OBS", { count })
        )
      );
    }
    controls.append(info);

    title.remove();
    heading.append(title, controls);
    card.append(heading);
  }

  function pollHistorySummaryCard(candidate) {
    const card = summaryCard(
      translate("candidate.poll_history", "POLL HISTORY"),
      "candidate-signals-poll-history-summary"
    );
    const history = pollHistoryForDisplay(candidate.poll_history);
    pollHistoryCardHeading(card, history);

    if (!history) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state candidate-signals-poll-history-state",
          translate("candidate.poll_history_unavailable", "Poll history unavailable.")
        )
      );
      return card;
    }

    if (history.evidence_state === "not_observed") {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state candidate-signals-poll-history-state",
          translate(
            "candidate.no_package_poll_history_evidence",
            "No package-level poll history evidence."
          )
        )
      );
      return card;
    }

    const visual = createElement(
      "div",
      "candidate-signals-poll-history-visual"
    );
    const legend = createElement(
      "div",
      "candidate-signals-poll-history-legend"
    );
    legend.append(
      createElement(
        "span",
        "candidate-signals-poll-history-legend-point",
        translate("candidate.poll_history_exact", "● exact")
      ),
      createElement(
        "span",
        "candidate-signals-poll-history-legend-range",
        translate("candidate.poll_history_published_range", "│ published range")
      )
    );
    visual.append(legend, pollHistoryChart(history, candidate));

    card.append(visual);
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
    const reported = evidence?.evidence_state === "reported";

    if (!reported) {
      row.className += " is-unavailable";

      const head = createElement(
        "div",
        "candidate-signals-attention-row-head"
      );
      head.append(
        createElement(
          "span",
          "candidate-signals-attention-label",
          label
        )
      );

      row.append(
        head,
        createElement(
          "span",
          "candidate-signals-attention-detail",
          tone === "general"
            ? translate(
              "candidate.no_current_general_visibility_evidence",
              "No current general visibility evidence."
            )
            : translate(
              "candidate.no_current_campaign_election_evidence",
              "No current campaign/election evidence."
            )
        )
      );
      return row;
    }

    const share = percentageNumber(evidence.share, true);
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
        share === null
          ? MISSING
          : percentageText(evidence.share, true)
      )
    );

    const compactParts = [
      hasValue(evidence.record_count)
        ? translate(
          "candidate.record_abbreviation",
          "{count} REC",
          { count: numberText(evidence.record_count) }
        )
        : null,
      hasValue(evidence.publisher_count)
        ? translate(
          "candidate.publisher_abbreviation",
          "{count} PUB",
          { count: numberText(evidence.publisher_count) }
        )
        : null,
      hasValue(evidence.active_day_count)
        ? translate(
          "candidate.active_day_abbreviation",
          "{count} {count, plural, one {DAY} other {DAYS}}",
          { count: numberText(evidence.active_day_count) }
        )
        : null
    ].filter(Boolean);

    const detail = createElement(
      "span",
      "candidate-signals-attention-detail",
      compactParts.join(" · ")
    );
    detail.setAttribute(
      "aria-label",
      [
        counted(evidence.record_count, "record"),
        hasValue(evidence.publisher_count)
          ? counted(evidence.publisher_count, "publisher")
          : null,
        hasValue(evidence.active_day_count)
          ? counted(evidence.active_day_count, "active_day")
          : null
      ].filter(Boolean).join(", ")
    );

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


  function visibilityHistoryState(message) {
    return createElement(
      "div",
      "candidate-signals-history-state",
      message
    );
  }

  function visibilityHistoryRecord(
    candidate,
    historyState
  ) {
    if (
      historyState?.status !== "ready" ||
      !Array.isArray(
        historyState.payload?.candidates
      )
    ) {
      return null;
    }

    return (
      historyState.payload.candidates.find(
        item =>
          item.candidate_id ===
            candidate.candidate_id
      ) || null
    );
  }

  function visibilityHistoryChart(
    candidate,
    historyState,
    laneName,
    tone,
    laneLabel
  ) {
    const block = createElement(
      "div",
      `candidate-signals-history-mini is-${tone}`
    );

    block.dataset.historyLane = laneName;

    const meta = createElement(
      "div",
      "candidate-signals-history-meta"
    );

    meta.append(
      createElement(
        "span",
        "candidate-signals-history-kicker",
        translate("candidate.daily_share_29d", "29D DAILY SHARE")
      )
    );

    const period =
      historyState?.status === "ready"
        ? historyState.payload?.period
        : null;

    if (hasValue(period?.data_as_of)) {
      meta.append(
        createElement(
          "span",
          "candidate-signals-history-asof",
          translate(
            "candidate.through_date",
            "THROUGH {date}",
            {
              date: formatDisplayDate(period.data_as_of)
                .toLocaleUpperCase(localeTag())
            }
          )
        )
      );
    }

    block.append(meta);

    if (historyState?.status === "loading") {
      block.append(
        skeletonPresentation(
          "list",
          translate(
            "candidate.loading_daily_share_29d",
            "Loading 29-day daily share"
          )
        )
      );
      return block;
    }

    if (historyState?.status !== "ready") {
      block.append(
        visibilityHistoryState(
          translate(
            "candidate.daily_share_history_unavailable",
            "29-day daily-share history unavailable."
          )
        )
      );
      return block;
    }

    const record =
      visibilityHistoryRecord(
        candidate,
        historyState
      );

    const series =
      record?.[laneName]?.daily_series;

    const denominators =
      historyState.payload?.lanes?.[
        laneName
      ]?.daily_denominators;

    if (
      !Array.isArray(series) ||
      series.length !== 29 ||
      !Array.isArray(denominators) ||
      denominators.length !== 29
    ) {
      block.append(
        visibilityHistoryState(
          translate(
            "candidate.complete_daily_share_history_unavailable",
            "Complete 29-day daily-share history unavailable."
          )
        )
      );
      return block;
    }

    const denominatorByDate =
      new Map(
        denominators.map(
          point => [
            point.date,
            point
          ]
        )
      );

    const observedShares =
      series
        .filter(
          point =>
            point &&
            point.share !== null &&
            Number.isFinite(
              Number(point.share)
            )
        )
        .map(
          point => Number(point.share)
        );

    if (!observedShares.length) {
      block.append(
        visibilityHistoryState(
          translate(
            "candidate.no_qualifying_lane_records",
            "No qualifying lane records in this 29-day window."
          )
        )
      );
      return block;
    }

    const maximum =
      Math.max(...observedShares);

    const scaleMaximum =
      maximum > 0
        ? maximum
        : 1;

    const width = 260;
    const height = 42;

    const margin = {
      top: 3,
      right: 2,
      bottom: 3,
      left: 2
    };

    const usableWidth =
      width -
      margin.left -
      margin.right;

    const usableHeight =
      height -
      margin.top -
      margin.bottom;

    const xFor = index =>
      margin.left +
      (
        usableWidth *
        (
          series.length <= 1
            ? 0
            : index /
              (series.length - 1)
        )
      );

    const yFor = share =>
      margin.top +
      (
        usableHeight *
        (
          1 -
          (
            Number(share) /
            scaleMaximum
          )
        )
      );

    const svg = wikipediaSvgElement(
      "svg",
      "candidate-signals-history-chart"
    );

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
      translate(
        "candidate.visibility_history_chart_aria",
        "{lane} daily share of lane coverage for {candidate}, {start} through {end}. Each point is candidate-linked records divided by all records in this lane. Gaps mark days with no lane denominator.",
        {
          lane: laneLabel,
          candidate: candidate.candidate_name,
          start: formatDisplayDate(series[0].date),
          end: formatDisplayDate(series[series.length - 1].date)
        }
      )
    );

    const baseline = wikipediaSvgElement(
      "line",
      "candidate-signals-history-baseline"
    );

    baseline.setAttribute(
      "x1",
      margin.left
    );

    baseline.setAttribute(
      "x2",
      width - margin.right
    );

    baseline.setAttribute(
      "y1",
      height - margin.bottom
    );

    baseline.setAttribute(
      "y2",
      height - margin.bottom
    );

    baseline.setAttribute(
      "aria-hidden",
      "true"
    );

    svg.append(baseline);

    const segments = [];
    let currentSegment = [];

    const flushSegment = () => {
      if (currentSegment.length) {
        segments.push(
          currentSegment
        );
        currentSegment = [];
      }
    };

    series.forEach(
      (point, index) => {
        if (
          point.share === null ||
          !Number.isFinite(
            Number(point.share)
          )
        ) {
          flushSegment();
          return;
        }

        currentSegment.push({
          index,
          point
        });
      }
    );

    flushSegment();

    segments.forEach(segment => {
      const line = wikipediaSvgElement(
        "polyline",
        `candidate-signals-history-line is-${tone}`
      );

      line.setAttribute(
        "points",
        segment.map(
          item =>
            `${xFor(
              item.index
            ).toFixed(2)},${yFor(
              item.point.share
            ).toFixed(2)}`
        ).join(" ")
      );

      line.setAttribute(
        "aria-hidden",
        "true"
      );

      svg.append(line);
    });

    series.forEach(
      (point, index) => {
        if (
          point.share === null ||
          !Number.isFinite(
            Number(point.share)
          )
        ) {
          return;
        }

        const denominator =
          denominatorByDate.get(
            point.date
          );

        const label = translate(
          "candidate.visibility_history_point",
          "{lane}, {date}: daily share {share}; candidate {records}; {publishers}; lane denominator {denominator}.",
          {
            lane: laneLabel,
            date: formatDisplayDate(point.date),
            share: percentageText(point.share, true),
            records: counted(point.record_count, "record"),
            publishers: counted(point.publisher_count, "publisher"),
            denominator: counted(denominator?.record_count, "record")
          }
        );

        const marker = wikipediaSvgElement(
          "circle",
          `candidate-signals-history-point is-${tone}`
        );

        marker.setAttribute(
          "cx",
          xFor(index)
        );

        marker.setAttribute(
          "cy",
          yFor(point.share)
        );

        marker.setAttribute(
          "r",
          index === series.length - 1
            ? 2
            : 1.35
        );

        marker.setAttribute(
          "aria-label",
          label
        );
        marker.setAttribute(
          "data-fr27-tooltip",
          label
        );
        svg.append(marker);
      }
    );

    block.append(svg);
    return block;
  }

  function attentionSummaryCard(candidate, historyState) {
    const card = summaryCard(
      translate("candidate.campaign_attention", "CAMPAIGN ATTENTION"),
      "candidate-signals-attention-summary"
    );

    const campaignReported =
      candidate.campaign_attention?.evidence_state === "reported";
    const generalReported =
      candidate.general_visibility?.evidence_state === "reported";

    if (!campaignReported && !generalReported) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          translate(
            "candidate.no_current_visibility_evidence",
            "No current campaign/election or general visibility evidence."
          )
        )
      );
    }

    const campaignShare = campaignReported
      ? percentageNumber(candidate.campaign_attention.share, true)
      : null;
    const generalShare = generalReported
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
    const campaignRow =
      attentionVisualRow(
        translate("candidate.campaign_election", "Campaign / election"),
        candidate.campaign_attention,
        "primary",
        scaleMaximum
      );

    campaignRow.append(
      visibilityHistoryChart(
        candidate,
        historyState,
        "campaign_attention",
        "primary",
        translate("candidate.campaign_election", "Campaign / election")
      )
    );

    const generalRow =
      attentionVisualRow(
        translate("candidate.general_visibility", "General visibility"),
        candidate.general_visibility,
        "general",
        scaleMaximum
      );

    generalRow.append(
      visibilityHistoryChart(
        candidate,
        historyState,
        "general_visibility",
        "general",
        translate("candidate.general_visibility", "General visibility")
      )
    );

    visual.append(
      campaignRow,
      generalRow
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
    const card = summaryCard(
      translate("candidate.race_coverage_mix", "RACE COVERAGE MIX"),
      "candidate-signals-composition-card"
    );
    const composition = scopeComposition(candidate);
    const [campaign, election] = composition.values;

    if (!composition.anyPublished) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          translate(
            "candidate.no_campaign_election_evidence_observed_in_the_current_period",
            "No campaign/election evidence observed in the current period."
          )
        )
      );
      return card;
    }

    if (composition.complete) {
      const summary = createElement(
        "div",
        "candidate-signals-composition-summary"
      );
      const summaryValue = createElement(
        "span",
        "candidate-signals-composition-summary-value"
      );
      summaryValue.append(
        createElement(
          "strong",
          "candidate-signals-composition-summary-count",
          numberText(composition.total)
        ),
        createElement(
          "span",
          "candidate-signals-composition-summary-unit",
          translate("candidate.records_abbreviation", "REC")
        )
      );

      semanticMetadata(
        summary,
        translate(
          "candidate.candidate_linked_race_records",
          "{count} candidate-linked campaign/election records",
          { count: numberText(composition.total) }
        )
      );

      summary.append(summaryValue);
      card.append(summary);
    }

    const visual = createElement(
      "div",
      "candidate-signals-composition-visual"
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
        ? translate(
          "candidate.race_coverage_composition_aria",
          "Race coverage composition: {campaign} campaign, {election} election",
          {
            campaign: numberText(campaign),
            election: numberText(election)
          }
        )
        : translate(
          "candidate.race_coverage_composition_is_incomplete",
          "Race coverage composition is incomplete"
        )
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
        translate("candidate.campaign_268286d2", "Campaign"),
        campaign,
        composition.total,
        "campaign",
        composition.complete
      ),
      scopeLegendRow(
        translate("candidate.election_4e5c805d", "Election"),
        election,
        composition.total,
        "election",
        composition.complete
      )
    );

    visual.append(stack, legend);
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
    const onOpenScrutiny = arguments[1];
    const card = summaryCard(
      translate("candidate.scrutiny", "SCRUTINY"),
      "candidate-signals-scrutiny-summary",
      "div"
    );

    if (typeof onOpenScrutiny === "function") {
      card.className += " is-operable";
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-haspopup", "dialog");
      card.setAttribute("aria-expanded", "false");
      card.setAttribute(
        "aria-label",
        translate(
          "candidate.open_claim_scrutiny_for_candidate",
          "Open claim scrutiny details for {candidate}",
          { candidate: candidate.candidate_name }
        )
      );

      const openScrutiny = () => {
        onOpenScrutiny(candidate, card);
      };

      card.addEventListener("click", openScrutiny);
      card.addEventListener("keydown", event => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        openScrutiny();
      });
    }

    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;

    if (!latest && !archive) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          translate(
            "candidate.no_scrutiny_evidence_is_currently_published",
            "No scrutiny evidence is currently published."
          )
        )
      );
      return card;
    }

    const matrix = createElement(
      "div",
      "candidate-signals-scrutiny-matrix"
    );
    matrix.append(
      createElement(
        "span",
        "candidate-signals-scrutiny-corner",
        ""
      ),
      semanticMetadata(
        createElement(
          "span",
          "candidate-signals-scrutiny-column",
          translate("candidate.about", "ABOUT")
        ),
        SCRUTINY_ABOUT_SEMANTICS
      ),
      semanticMetadata(
        createElement(
          "span",
          "candidate-signals-scrutiny-column",
          translate("candidate.by", "BY")
        ),
        SCRUTINY_BY_SEMANTICS
      ),
      semanticMetadata(
        createElement(
          "span",
          "candidate-signals-scrutiny-column",
          translate("candidate.reviews_abbreviation", "REV.")
        ),
        translate("candidate.reviews", "REVIEWS"),
        translate("candidate.reviews", "REVIEWS")
      )
    );

    if (latest) {
      matrix.append(
        createElement(
          "span",
          "candidate-signals-scrutiny-row-label is-current",
          translate("candidate.days_14", "14 DAYS")
        ),
        scrutinyMatrixCell(
          latest.about_count,
          "is-current"
        ),
        scrutinyMatrixCell(
          latest.by_count,
          "is-current"
        ),
        scrutinyMatrixCell(
          latest.review_count,
          "is-current"
        )
      );
    }

    if (archive) {
      matrix.append(
        createElement(
          "span",
          "candidate-signals-scrutiny-row-label is-archive",
          translate("candidate.archive", "ARCHIVE")
        ),
        scrutinyMatrixCell(
          archive.about_count,
          "is-archive"
        ),
        scrutinyMatrixCell(
          archive.by_count,
          "is-archive"
        ),
        scrutinyMatrixCell(
          archive.review_count,
          "is-archive"
        )
      );
    }

    card.append(matrix);

    const newestDate =
      latest?.newest_review_date || archive?.newest_review_date;

    if (newestDate) {
      const title = card.querySelector(
        ".candidate-signals-analysis-card-title"
      );
      if (title) {
        const latestReviewText = translate(
          "candidate.latest_review_value",
          "LATEST REVIEW · {date}",
          { date: formatDisplayDate(newestDate) }
        );
        semanticMetadata(
          title,
          latestReviewText,
          translate(
            "candidate.scrutiny_latest_review_aria",
            "SCRUTINY — {latest}",
            { latest: latestReviewText }
          )
        );
      }
    }

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
        translate("candidate.match_basis", "Match basis")
      ),
      createElement(
        "span",
        "candidate-signals-evidence-ratio-detail",
        published
          ? translate(
            "candidate.match_basis_counts",
            "{headline} headline · {summary} summary-only",
            {
              headline: numberText(headline),
              summary: numberText(summaryOnly)
            }
          )
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
    const reported = campaign?.evidence_state === "reported";

    const head = createElement(
      "div",
      "candidate-signals-evidence-structure-head"
    );
    head.append(
      createElement(
        "h3",
        "candidate-signals-subsection-title",
        translate("candidate.evidence_structure", "EVIDENCE STRUCTURE")
      )
    );

    const period = metadata?.visibility?.current_period;
    head.append(
      createElement(
        "span",
        "candidate-signals-evidence-structure-period",
        period
          ? formatDateRange(period.start_date, period.end_date)
          : translate(
            "candidate.current_published_period",
            "Current published period"
          )
      )
    );

    section.append(head);

    if (!reported) {
      section.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          translate(
            "candidate.no_campaign_election_evidence_observed_in_the_current_period",
            "No campaign/election evidence observed in the current period."
          )
        )
      );
      return section;
    }

    const stats = createElement(
      "div",
      "candidate-signals-evidence-structure-stats"
    );
    stats.append(
      evidenceStructureStat(
        translate("candidate.records", "Records"),
        numberText(campaign.record_count)
      ),
      evidenceStructureStat(
        translate("candidate.publishers", "Publishers"),
        numberText(campaign.publisher_count)
      ),
      evidenceStructureStat(
        translate("candidate.active_days", "Active days"),
        numberText(campaign.active_day_count)
      ),
      evidenceStructureStat(
        translate("candidate.story_clusters", "Story clusters"),
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
        translate("candidate.top_publisher", "Top publisher"),
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
        translate("candidate.top_story_concentration", "Top story concentration"),
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
    return `${numeric > 0 ? "+" : ""}${formatLocaleNumber(
      numeric / 100,
      {
        style: "percent",
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
      }
    )}`;
  }

  function wikipediaAttentionFlagLabel(value) {
    const labels = {
      sustained_rise: translate("candidate.wikipedia.state.sustained_rise", "SUSTAINED RISE"),
      sustained_decline: translate("candidate.wikipedia.state.sustained_decline", "SUSTAINED DECLINE"),
      event_amplified: translate("candidate.wikipedia.state.event_amplified", "EVENT AMPLIFIED"),
      stable: translate("candidate.wikipedia.state.stable", "STABLE"),
      low_attention: translate("candidate.wikipedia.state.low_attention", "LOW ATTENTION")
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

    if (absolute >= 1000) {
      return formatLocaleNumber(numeric, {
        notation: "compact",
        compactDisplay: "short",
        maximumFractionDigits: absolute >= 10000 ? 0 : 1
      });
    }

    return groupedNumberText(numeric);
  }

  function wikipediaShortDate(value) {
    if (!hasValue(value)) return MISSING;

    const date = new Date(`${value}T00:00:00Z`);

    if (!Number.isFinite(date.getTime())) {
      return String(value);
    }

    return new Intl.DateTimeFormat(localeTag(), {
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
        translate("candidate.wikipedia.state", "STATE")
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
        translate("candidate.wikipedia.daily_pageviews", "DAILY PAGEVIEWS")
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
      translate(
        "candidate.wikipedia.chart_aria",
        "French Wikipedia daily pageviews for {candidate}, {start} through {end}. Thirty-day peak {views} views on {date}.",
        {
          candidate: candidate.candidate_name,
          start: formatDisplayDate(recent[0].date),
          end: formatDisplayDate(latestPoint.date),
          views: groupedNumberText(peak.views),
          date: formatDisplayDate(peak.date)
        }
      )
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

      const tooltip = translate(
        "candidate.wikipedia.point_tooltip",
        "{date} · {views} pageviews",
        {
          date: formatDisplayDate(point.date),
          views: groupedNumberText(point.views)
        }
      );

      marker.setAttribute("aria-label", tooltip);
      marker.setAttribute("data-fr27-tooltip", tooltip);

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
      translate(
        "candidate.wikipedia.attention_30_days",
        "WIKIPEDIA ATTENTION · 30 DAYS"
      )
    );


    const wikipediaTitleRow = createElement(
      "div",
      "candidate-signals-wikipedia-title-row"
    );

    const wikipediaInfo = createElement(
      "button",
      "candidate-signals-poll-evidence-info candidate-signals-wikipedia-info",
      "i"
    );

    wikipediaInfo.type = "button";
    wikipediaInfo.setAttribute(
      "aria-label",
      translate(
        "candidate.wikipedia.about_attention",
        "About Wikipedia attention"
      )
    );

    wikipediaTitleRow.append(
      headingTitle
    );

    heading.append(wikipediaTitleRow);

    head.append(heading);

    if (attentionState?.status === "loading") {
      section.append(
        head,
        skeletonPresentation(
          "agenda",
          translate(
            "candidate.wikipedia.loading_attention",
            "Loading published Wikimedia attention"
          )
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
      translate(
        "candidate.wikipedia.default_interpretation",
        "French Wikipedia pageviews measure article-reading attention."
      );

    const exclusions =
      Array.isArray(methodology?.not_measures)
        ? methodology.not_measures.filter(hasValue)
        : [];

    const methodologyNote = translate(
      "candidate.wikipedia.methodology",
      "Tracks daily pageviews of the candidate’s French Wikipedia article over the latest 30 days. {interpretation} Pageviews may include repeat visits.{exclusions}",
      {
        interpretation,
        exclusions: exclusions.length
          ? translate(
            "candidate.wikipedia.exclusions",
            " They do not measure {values}.",
            { values: exclusions.join(", ") }
          )
          : ""
      }
    );

    explanatoryMetadata(wikipediaInfo, methodologyNote);
    wikipediaTitleRow.append(wikipediaInfo);

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
          translate(
            "candidate.wikipedia.attention_unavailable",
            "Published Wikipedia attention is unavailable for this candidate."
          )
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
          translate(
            "candidate.wikipedia.series_unavailable",
            "A complete 30-day Wikipedia attention series is unavailable."
          )
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
        translate(
          "candidate.wikipedia.data_through",
          "DATA THROUGH {date}",
          {
            date: formatDisplayDate(periodDate)
              .toLocaleUpperCase(localeTag())
          }
        )
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
        translate("candidate.wikipedia.latest_7d", "LATEST 7D"),
        groupedNumberText(
          record.latest_7_views
        )
      ),
      wikipediaAttentionMetric(
        translate("candidate.wikipedia.previous_7d", "PREVIOUS 7D"),
        groupedNumberText(
          record.previous_7_views
        )
      ),
      wikipediaAttentionMetric(
        translate("candidate.wikipedia.change_7d", "7D CHANGE"),
        wikipediaSignedPercent(
          record.change_7_pct
        ),
        `is-${wikipediaChangeTone(
          record.change_7_pct
        )}`
      ),
      wikipediaAttentionMetric(
        translate("candidate.wikipedia.peak_30d", "30D PEAK"),
        groupedNumberText(peak.views)
      ),
      wikipediaAttentionMetric(
        translate("candidate.wikipedia.peak_date", "PEAK DATE"),
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
        translate("candidate.wikipedia.peak_removed_7d", "PEAK-REMOVED 7D"),
        wikipediaSignedPercent(
          record.change_7_peak_removed_pct
        ),
        `is-${wikipediaChangeTone(
          record.change_7_peak_removed_pct
        )}`
      ),
      wikipediaAttentionMetric(
        translate("candidate.wikipedia.total_28d", "28D TOTAL"),
        groupedNumberText(
          record.latest_28_views
        )
      ),
      wikipediaAttentionMetric(
        translate("candidate.wikipedia.change_28d", "28D CHANGE"),
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


  function selectedAnalysis(
    candidate,
    metadata,
    attentionState,
    visibilityHistoryState,
    agendaHistoryState,
    onOpenScrutiny
  ) {
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
        ? translate(
          "candidate.updated_date",
          "Updated {date}",
          { date: formatDisplayDate(updateDate) }
        )
        : null
    );
    header.querySelector("h2").id = "candidate-signals-analysis-title";

    const cards = createElement(
      "div",
      "candidate-signals-analysis-cards has-poll-history"
    );
    const agendaProfile = currentAgendaSummaryCard(candidate);

    if (agendaProfile) {
      cards.className += " has-agenda-profile";
      cards.append(
        pollSummaryCard(candidate, metadata),
        pollHistorySummaryCard(candidate),
        agendaProfile,
        historicalAgendaSummaryCard(
          candidate,
          agendaHistoryState
        ),
        attentionSummaryCard(
          candidate,
          visibilityHistoryState
        ),
        scopeCompositionCard(candidate),
        scrutinySummaryCard(candidate, onOpenScrutiny)
      );
    } else {
      cards.append(
        pollSummaryCard(candidate, metadata),
        pollHistorySummaryCard(candidate),
        attentionSummaryCard(
          candidate,
          visibilityHistoryState
        ),
        scopeCompositionCard(candidate),
        scrutinySummaryCard(candidate, onOpenScrutiny)
      );
    }

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
    const labelNode = createElement(
      "span",
      "candidate-signals-dossier-metric-label",
      label
    );

    const valueNode = createElement(
      "strong",
      "candidate-signals-dossier-metric-value",
      primary
    );

    const noteList = (
      Array.isArray(notes) ? notes : [notes]
    ).filter(hasValue);

    metric.append(labelNode);

    if (noteList.length) {
      const infoText = `${noteList.join(". ")}${
        noteList.at(-1).endsWith(".") ? "" : "."
      }`;

      const info = createElement(
        "button",
        "candidate-signals-poll-evidence-info candidate-signals-dossier-metric-info",
        ""
      );

      info.setAttribute("type", "button");

      explanatoryMetadata(
        info,
        infoText,
        translate(
          "candidate.metric_details_aria",
          "{label} details. {details}",
          { label, details: infoText }
        )
      );

      metric.append(info);
    }

    metric.append(valueNode);

    /*
     * Preserve the existing note nodes for data/test continuity,
     * but remove them from the visual card. The same information
     * is exposed through the explicit tooltip trigger.
     */
    const noteWrap = createElement(
      "span",
      "candidate-signals-dossier-metric-notes"
    );

    noteWrap.hidden = true;

    noteList.forEach(note => {
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
      [translate("candidate.point_estimate", "Point estimate"), hasPointEstimate
        ? percentageText(polling.selected_hypothesis_score)
        : hasPublishedRange
          ? translate("candidate.range_only", "Range only")
          : reported
            ? MISSING
            : NOT_TESTED],
      [translate("candidate.published_range", "Published range"), reported
        ? rangeText(polling.range_min, polling.range_max)
        : NOT_TESTED],
      [translate("candidate.pollster", "Pollster"), pollPackage?.pollster || MISSING],
      [translate("candidate.field_dates", "Field dates"), formatDateRange(
        pollPackage?.fieldwork_start,
        pollPackage?.fieldwork_end
      )],
      [translate("candidate.sample", "Sample"), hasValue(pollPackage?.sample_size)
        ? groupedNumberText(pollPackage.sample_size)
        : MISSING],
      [translate("candidate.hypotheses_heading", "Hypotheses"), reported && hasValue(polling.hypothesis_count)
        ? numberText(polling.hypothesis_count)
        : reported
          ? MISSING
          : NOT_TESTED],
      [translate("candidate.published_sources", "Published sources"), hasValue(sourceCount)
        ? numberText(sourceCount)
        : MISSING]
    ];
  }

  function dossierStructureLines(evidence) {
    const concentration = evidence?.concentration;
    return [
      [translate("candidate.publishers", "Publishers"), evidence
        ? numberText(evidence.publisher_count)
        : MISSING],
      [translate("candidate.active_days", "Active days"), evidence
        ? numberText(evidence.active_day_count)
        : MISSING],
      [translate("candidate.story_clusters", "Story clusters"), evidence
        ? numberText(evidence.story_cluster_count)
        : MISSING],
      [translate("candidate.leading_publisher", "Leading publisher"), concentration && hasValue(
        concentration.leading_publisher
      ) ? concentration.leading_publisher : MISSING],
      [translate("candidate.publisher_concentration", "Publisher concentration"), concentration
        ? percentageText(
          concentration.leading_publisher_share,
          true
        )
        : MISSING],
      [translate("candidate.story_concentration", "Story concentration"), concentration
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
    const lines = [];

    if (latest) {
      lines.push(
        [translate("candidate.scrutiny.latest_about", "14 days · ABOUT"), numberText(latest.about_count)],
        [translate("candidate.scrutiny.latest_by", "14 days · BY"), numberText(latest.by_count)],
        [translate("candidate.scrutiny.latest_reviews", "14 days · Reviews"), numberText(latest.review_count)]
      );
    }

    if (archive) {
      lines.push(
        [translate("candidate.scrutiny.archive_about", "Archive · ABOUT"), numberText(archive.about_count)],
        [
          translate("candidate.scrutiny.archive_by", "Archive · BY"),
          numberText(archive.by_count)
        ],
        [translate("candidate.scrutiny.archive_reviews", "Archive · Reviews"), numberText(archive.review_count)]
      );
    }

    if (newestDate) {
      lines.push([
        translate("candidate.newest_review", "Newest review"),
        formatDisplayDate(newestDate)
      ]);
    }

    return lines;
  }

  function compactEvidenceDetails(candidate, metadata) {
    const details = createElement(
      "details",
      "candidate-signals-dossier-details"
    );
    const summary = createElement(
      "summary",
      "candidate-signals-dossier-details-summary",
      translate(
        "candidate.view_full_evidence_details",
        "View full evidence details"
      )
    );
    const content = createElement(
      "div",
      "candidate-signals-dossier-details-content"
    );

    const campaignReported =
      candidate.campaign_attention?.evidence_state === "reported";
    const generalReported =
      candidate.general_visibility?.evidence_state === "reported";
    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;

    content.append(
      evidenceGroup(
        translate(
          "candidate.poll_evidence_source_details",
          "POLL EVIDENCE & SOURCE DETAILS"
        ),
        dossierPollLines(candidate, metadata)
      ),
      campaignReported
        ? evidenceGroup(
          translate(
            "candidate.campaign_election_structure",
            "CAMPAIGN / ELECTION STRUCTURE"
          ),
          dossierStructureLines(candidate.campaign_attention)
        )
        : evidenceStateGroup(
          translate(
            "candidate.campaign_election_structure",
            "CAMPAIGN / ELECTION STRUCTURE"
          ),
          translate(
            "candidate.no_current_campaign_election_evidence",
            "No current campaign/election evidence."
          )
        ),
      generalReported
        ? evidenceGroup(
          translate("candidate.general_structure", "GENERAL STRUCTURE"),
          dossierStructureLines(candidate.general_visibility)
        )
        : evidenceStateGroup(
          translate("candidate.general_structure", "GENERAL STRUCTURE"),
          translate(
            "candidate.no_current_general_visibility_evidence",
            "No current general visibility evidence."
          )
        ),
      latest || archive
        ? evidenceGroup(
          translate(
            "candidate.claim_scrutiny_detail",
            "CLAIM SCRUTINY DETAIL"
          ),
          dossierScrutinyLines(candidate)
        )
        : evidenceStateGroup(
          translate(
            "candidate.claim_scrutiny_detail",
            "CLAIM SCRUTINY DETAIL"
          ),
          translate(
            "candidate.no_scrutiny_evidence_currently_published",
            "No scrutiny evidence currently published."
          )
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
    const card = createElement(
      "section",
      "candidate-signals-dossier-card candidate-signals-dossier-visibility"
    );
    card.append(
      createElement(
        "h3",
        "candidate-signals-dossier-card-title",
        translate("candidate.visibility_composition", "VISIBILITY & COMPOSITION")
      )
    );

    const campaign = candidate.campaign_attention;
    const general = candidate.general_visibility;
    const campaignReported =
      campaign?.evidence_state === "reported";
    const generalReported =
      general?.evidence_state === "reported";

    if (!campaignReported && !generalReported) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          translate(
            "candidate.no_current_visibility_evidence",
            "No current campaign/election or general visibility evidence."
          )
        )
      );
      return card;
    }

    const composition = scopeComposition(candidate);
    const [campaignCount, electionCount] =
      composition.values;

    if (campaignReported && composition.anyPublished) {
      const totalLine = createElement(
        "div",
        "candidate-signals-dossier-visibility-total"
      );
      const totalText = composition.complete
        ? numberText(composition.total)
        : translate("candidate.incomplete", "Incomplete");

      totalLine.append(
        createElement(
          "strong",
          `candidate-signals-dossier-visibility-total-value${
            composition.complete ? "" : " is-textual"
          }`,
          totalText
        ),
        createElement(
          "span",
          "candidate-signals-dossier-visibility-total-label",
          translate("candidate.race_records_title", "Race records")
        )
      );
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
        [electionCount, "election"]
      ].forEach(([count, tone]) => {
        const segment = createElement(
          "span",
          `candidate-signals-dossier-composition-segment is-${tone}`
        );
        const width = (
          composition.complete &&
          composition.total > 0 &&
          count !== null
        )
          ? (count / composition.total) * 100
          : 0;

        segment.style.width =
          `${Math.max(0, Math.min(100, width))}%`;
        stack.append(segment);
      });
      card.append(stack);

      const scopeGrid = createElement(
        "div",
        "candidate-signals-dossier-scope-grid"
      );
      scopeGrid.append(
        dossierScopeCell(
          translate("candidate.campaign_268286d2", "Campaign"),
          campaignCount,
          composition.total,
          "campaign",
          composition.complete
        ),
        dossierScopeCell(
          translate("candidate.election_4e5c805d", "Election"),
          electionCount,
          composition.total,
          "election",
          composition.complete
        )
      );
      card.append(scopeGrid);
    }

    const summary = createElement(
      "div",
      "candidate-signals-dossier-visibility-summary"
    );

    if (campaignReported) {
      summary.append(
        summaryMeta(
          translate("candidate.campaign_election", "Campaign / election"),
          `${counted(campaign.record_count, "record")} · ${percentageText(
            campaign.share,
            true
          )}`
        )
      );
    }

    if (generalReported) {
      summary.append(
        summaryMeta(
          translate("candidate.general_visibility", "General visibility"),
          `${counted(general.record_count, "record")} · ${percentageText(
            general.share,
            true
          )}`,
          "is-general"
        )
      );
    }

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
        translate("candidate.evidence_structure", "EVIDENCE STRUCTURE")
      )
    );

    const campaign = candidate.campaign_attention;
    const reported = campaign?.evidence_state === "reported";

    if (!reported) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          translate(
            "candidate.no_campaign_election_evidence_observed_in_the_current_period",
            "No campaign/election evidence observed in the current period."
          )
        )
      );
      return card;
    }

    const stats = createElement(
      "div",
      "candidate-signals-structure-stats"
    );
    stats.append(
      dossierStructureStat(
        translate("candidate.records", "Records"),
        campaign && hasValue(campaign.record_count)
          ? numberText(campaign.record_count)
          : MISSING
      ),
      dossierStructureStat(
        translate("candidate.publishers", "Publishers"),
        campaign && hasValue(campaign.publisher_count)
          ? numberText(campaign.publisher_count)
          : MISSING
      ),
      dossierStructureStat(
        translate("candidate.active_days", "Active days"),
        campaign && hasValue(campaign.active_day_count)
          ? numberText(campaign.active_day_count)
          : MISSING
      ),
      dossierStructureStat(
        translate("candidate.story_clusters", "Story clusters"),
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
        translate("candidate.top_publisher", "Top publisher"),
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
        translate("candidate.top_story_concentration", "Top story concentration"),
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

  function dossierScrutinyMetric(relationshipKind, label, value) {
    const metric = createElement(
      "span",
      "candidate-signals-dossier-scrutiny-metric"
    );
    const valueClass = (
      hasValue(value) && Number.isFinite(Number(value)) && Number(value) === 0
    ) ? " is-zero" : "";
    const labelNode = createElement(
      "span",
      "candidate-signals-dossier-scrutiny-label",
      label
    );
    if (relationshipKind === "about") {
      semanticMetadata(labelNode, SCRUTINY_ABOUT_SEMANTICS);
    } else if (relationshipKind === "by") {
      semanticMetadata(labelNode, SCRUTINY_BY_SEMANTICS);
    }
    metric.append(
      createElement(
        "strong",
        `candidate-signals-dossier-scrutiny-value${valueClass}`,
        hasValue(value) ? numberText(value) : MISSING
      ),
      labelNode
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
      dossierScrutinyMetric(
        "about",
        translate("candidate.about", "ABOUT"),
        evidence?.about_count
      ),
      dossierScrutinyMetric(
        "by",
        translate("candidate.by", "BY"),
        evidence?.by_count
      ),
      dossierScrutinyMetric(
        "reviews",
        translate("candidate.reviews", "REVIEWS"),
        evidence?.review_count
      )
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
        translate("candidate.scrutiny_overview", "SCRUTINY OVERVIEW")
      )
    );

    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;

    if (!latest && !archive) {
      card.append(
        createElement(
          "p",
          "candidate-signals-card-state",
          translate(
            "candidate.no_scrutiny_evidence_is_currently_published",
            "No scrutiny evidence is currently published."
          )
        )
      );
      return card;
    }

    const newestDate = (
      latest?.newest_review_date || archive?.newest_review_date
    );
    const grid = createElement(
      "div",
      "candidate-signals-dossier-scrutiny-grid"
    );

    if (latest) {
      grid.append(
        dossierScrutinyPeriod(
          translate("candidate.days_14", "14 DAYS"),
          latest,
          "is-current"
        )
      );
    }

    if (archive) {
      grid.append(
        dossierScrutinyPeriod(
          translate("candidate.archive", "ARCHIVE"),
          archive,
          "is-archive"
        )
      );
    }

    if (newestDate) {
      const review = createElement(
        "section",
        "candidate-signals-dossier-scrutiny-block is-review"
      );
      review.append(
        createElement(
          "h4",
          "candidate-signals-scrutiny-period-title",
          translate("candidate.latest_review", "LATEST REVIEW")
        ),
        createElement(
          "strong",
          "candidate-signals-dossier-review-date",
          formatDisplayDate(newestDate)
        ),
        createElement(
          "span",
          "candidate-signals-dossier-review-note",
          translate("candidate.published_review_date", "Published review date")
        )
      );
      grid.append(review);
    }

    card.append(grid);
    return card;
  }

  function dossierLatestDevelopment(candidate) {
    const section = createElement(
      "section",
      "candidate-signals-dossier-card candidate-signals-dossier-development"
    );
    section.append(
      explanatoryMetadata(
        createElement(
          "h3",
          "candidate-signals-dossier-card-title",
          translate("candidate.latest_development", "LATEST DEVELOPMENT")
        ),
        LATEST_DEVELOPMENT_EXPLANATION,
        translate(
          "candidate.latest_development_aria",
          "LATEST DEVELOPMENT — {explanation}",
          { explanation: LATEST_DEVELOPMENT_EXPLANATION }
        )
      )
    );

    const development = candidate.latest_development;
    if (!development || !hasValue(development.headline)) {
      section.append(
        createElement(
          "p",
          "candidate-signals-development-empty",
          translate(
            "candidate.no_source_linked_development_is_currently_published",
            "No source-linked development is currently published."
          )
        )
      );
      return section;
    }

    if (hasValue(development.coverage_scope)) {
      section.append(
        createElement(
          "span",
          "candidate-signals-dossier-development-scope",
          translate(
            `candidate.scope.${String(development.coverage_scope).toLowerCase()}`,
            String(development.coverage_scope)
          ).toLocaleUpperCase(localeTag())
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
        translate("candidate.open_latest_source", "Open latest source →")
      );
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      section.append(link);
    } else {
      section.append(
        evidenceLine(translate("candidate.source_link", "Source link"), MISSING)
      );
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
      translate("candidate.view_full_evidence", "View full evidence →")
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
        translate("candidate.selected_candidate", "SELECTED CANDIDATE")
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
          candidacyStatusLabel(status).toLocaleUpperCase(localeTag())
        )
      );
    }
    const tier = candidate.candidacy?.display_tier;
    if (hasValue(tier)) {
      badges.append(
        createElement(
          "span",
          `candidate-signals-dossier-tier is-${String(tier).toLowerCase()}`,
          candidacyTierLabel(tier).toLocaleUpperCase(localeTag())
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
    const campaignReported = campaign?.evidence_state === "reported";
    const hypothesisCount = pollReported && hasValue(poll.hypothesis_count)
      ? numberText(poll.hypothesis_count)
      : null;
    const period = metadata?.visibility?.current_period;
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

    const pollMetric = dossierMetric(
      translate("candidate.poll_evidence", "POLL EVIDENCE"),
      pollValue(candidate),
      pollReported
        ? [
          rangeText(poll.range_min, poll.range_max),
          hypothesisCount
            ? translate(
              "candidate.count.hypothesis",
              "{count} {count, plural, one {hypothesis} other {hypotheses}}",
              { count: hypothesisCount }
            )
            : null
        ]
        : [translate(
          "candidate.not_tested_in_featured_package",
          "Not tested in featured package"
        )]
    );

    const scrutinyMetric = latest
      ? dossierMetric(
        translate(
          "candidate.scrutiny_14_days_heading",
          "SCRUTINY · 14 DAYS"
        ),
        translate(
          "candidate.scrutiny_relationship_counts",
          "{about} about · {by} by",
          {
            about: numberText(latest.about_count),
            by: numberText(latest.by_count)
          }
        ),
        [
          counted(latest.review_count, "review"),
          newestDate
            ? translate(
              "candidate.latest_review_title_value",
              "Latest review · {date}",
              { date: formatDisplayDate(newestDate) }
            )
            : null
        ],
        "is-composite"
      )
      : dossierMetric(
        translate(
          "candidate.scrutiny_14_days_heading",
          "SCRUTINY · 14 DAYS"
        ),
        translate(
          "candidate.no_current_scrutiny_evidence",
          "No current scrutiny evidence."
        ),
        [],
        "is-composite is-empty"
      );

    if (campaignReported) {
      metrics.append(
        pollMetric,
        dossierMetric(
          translate("candidate.campaign_attention", "CAMPAIGN ATTENTION"),
          percentageText(campaign.share, true),
          [
            counted(campaign.record_count, "record"),
            counted(campaign.publisher_count, "publisher")
          ],
          "is-campaign-attention"
        ),
        scrutinyMetric,
        dossierMetric(
          translate("candidate.active_days_heading", "ACTIVE DAYS"),
          hasValue(campaign.active_day_count)
            ? numberText(campaign.active_day_count)
            : MISSING,
          [
            translate(
              "candidate.current_published_period",
              "Current published period"
            ),
            periodText
          ]
        )
      );
    } else {
      metrics.append(
        pollMetric,
        scrutinyMetric,
        dossierMetric(
          translate(
            "candidate.campaign_election_evidence",
            "CAMPAIGN / ELECTION EVIDENCE"
          ),
          translate(
            "candidate.no_current_campaign_election_evidence",
            "No current campaign/election evidence."
          ),
          periodText ? [periodText] : [],
          "is-empty is-wide"
        )
      );
    }

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
      mount.append(
        skeletonPresentation(
          "candidates",
          translate(
            "candidate.loading_candidate_evidence",
            "Loading candidate evidence"
          )
        )
      );
      return null;
    }
    if (status === "empty") {
      mount.append(
        statePresentation(translate(
          "candidate.no_candidate_evidence_is_currently_published",
          "No candidate evidence is currently published."
        ))
      );
      return null;
    }
    if (status === "unavailable") {
      mount.append(
        statePresentation(translate(
          "candidate.candidate_evidence_is_temporarily_unavailable",
          "Candidate evidence is temporarily unavailable."
        ))
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
        statePresentation(translate(
          "candidate.no_candidate_evidence_is_currently_published",
          "No candidate evidence is currently published."
        ))
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
          resolvePortrait: options.resolvePortrait,
          candidateAttention:
            options.candidateAttention,
          candidateVisibilityHistory:
            options.candidateVisibilityHistory,
          candidateAgendaHistory:
            options.candidateAgendaHistory,
          onOpenScrutiny:
            options.onOpenScrutiny
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
        options.candidateAttention,
        options.candidateVisibilityHistory,
        options.candidateAgendaHistory,
        options.onOpenScrutiny
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
