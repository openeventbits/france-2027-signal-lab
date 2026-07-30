(() => {
  "use strict";

  const MISSING = "Not published";
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

  function percentageText(value, ratio = false) {
    if (!hasValue(value) || !Number.isFinite(Number(value))) return MISSING;
    const amount = ratio ? Number(value) * 100 : Number(value);
    const rounded = Math.round((amount + Number.EPSILON) * 1000) / 1000;
    return `${rounded}%`;
  }

  function rangeText(minimum, maximum) {
    if (!hasValue(minimum) || !hasValue(maximum)) return MISSING;
    return `${percentageText(minimum)}–${percentageText(maximum)}`;
  }

  function pollValue(candidate) {
    const polling = candidate.polling;
    if (!polling) return MISSING;
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

  function regionHeader(title, note = null) {
    const header = createElement("header", "candidate-signals-region-header");
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

  function compositionLines(candidate) {
    const counts = candidate.campaign_attention?.scope_counts;
    return [
      ["Campaign", counts ? numberText(counts.campaign) : MISSING],
      ["Election", counts ? numberText(counts.election) : MISSING],
      ["General", counts ? numberText(counts.general) : MISSING]
    ];
  }

  function scrutinyLines(candidate) {
    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;
    return [
      ["14 days · BY", latest ? numberText(latest.by_count) : MISSING],
      ["14 days · ABOUT", latest ? numberText(latest.about_count) : MISSING],
      ["Archive · BY", archive ? numberText(archive.by_count) : MISSING],
      ["Archive · ABOUT", archive ? numberText(archive.about_count) : MISSING]
    ];
  }

  function pollLines(candidate, metadata) {
    const polling = candidate.polling;
    const pollPackage = metadata?.featured_polling_package;
    const lines = [
      ["Selected estimate", polling
        ? percentageText(polling.selected_hypothesis_score)
        : MISSING],
      ["Published range", polling
        ? rangeText(polling.range_min, polling.range_max)
        : MISSING]
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
      `Campaign/election ${campaign
        ? numberText(campaign.record_count)
        : MISSING}`,
      `General ${general ? numberText(general.record_count) : MISSING}`
    ].join(" · ");
  }

  function candidateMonitor(candidates, selectedId, options, chooseCandidate) {
    const section = createElement(
      "section",
      "candidate-signals-panel candidate-signals-monitor"
    );
    section.setAttribute("aria-labelledby", "candidate-signals-monitor-title");
    const header = regionHeader("CANDIDATE MONITOR");
    header.querySelector("h2").id = "candidate-signals-monitor-title";

    const list = createElement("div", "candidate-signals-monitor-list");
    list.setAttribute("aria-label", "Published candidates");
    candidates.forEach(candidate => {
      const selected = candidate.candidate_id === selectedId;
      const button = createElement(
        "button",
        `candidate-signals-candidate-button${selected ? " is-selected" : ""}`
      );
      button.type = "button";
      button.dataset.candidateSignalsCandidate = candidate.candidate_id;
      button.setAttribute("aria-pressed", String(selected));

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
      const nameBlock = createElement(
        "span",
        "candidate-signals-candidate-copy"
      );
      nameBlock.append(
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
      identity.append(nameBlock);

      const metric = createElement(
        "span",
        "candidate-signals-candidate-metric"
      );
      metric.append(
        createElement(
          "strong",
          "candidate-signals-candidate-poll",
          pollValue(candidate)
        ),
        createElement(
          "span",
          "candidate-signals-selection-label",
          selected ? "SELECTED" : "SELECT"
        )
      );
      button.append(identity, metric);
      list.append(button);
    });

    list
      .querySelectorAll(".candidate-signals-candidate-button")
      .forEach((button, index, buttons) => {
        button.addEventListener("click", () => {
          chooseCandidate(button.dataset.candidateSignalsCandidate, true);
        });
        button.addEventListener("keydown", event => {
          let nextIndex = null;
          if (event.key === "ArrowDown") {
            nextIndex = Math.min(index + 1, buttons.length - 1);
          }
          if (event.key === "ArrowUp") {
            nextIndex = Math.max(index - 1, 0);
          }
          if (event.key === "Home") nextIndex = 0;
          if (event.key === "End") nextIndex = buttons.length - 1;
          if (nextIndex === null) return;
          event.preventDefault();
          chooseCandidate(
            buttons[nextIndex].dataset.candidateSignalsCandidate,
            true
          );
        });
      });

    section.append(header, list);
    return section;
  }

  function analysisCard(title, primary, lines) {
    const card = createElement("section", "candidate-signals-analysis-card");
    card.append(
      createElement("h3", "candidate-signals-analysis-card-title", title),
      createElement("strong", "candidate-signals-analysis-primary", primary)
    );
    lines.forEach(item => {
      card.append(
        evidenceLine(item[0], item[1])
      );
    });
    return card;
  }

  function snapshotRow(label, value, percent = null, tone = "cyan") {
    const row = createElement("div", "candidate-signals-snapshot-row");
    row.append(
      createElement("span", "candidate-signals-snapshot-label", label),
      createElement("strong", "candidate-signals-snapshot-value", value)
    );
    if (hasValue(percent) && Number.isFinite(Number(percent))) {
      const track = createElement("span", "candidate-signals-snapshot-track");
      track.setAttribute("aria-hidden", "true");
      const fill = createElement(
        "span",
        `candidate-signals-snapshot-fill is-${tone}`
      );
      fill.style.width = `${Math.max(0, Math.min(100, Number(percent)))}%`;
      track.append(fill);
      row.append(track);
    } else {
      row.append(
        createElement("span", "candidate-signals-snapshot-no-track", "—")
      );
    }
    return row;
  }

  function evidenceSnapshot(candidate) {
    const section = createElement("section", "candidate-signals-snapshot");
    section.append(
      createElement(
        "h3",
        "candidate-signals-subsection-title",
        "EVIDENCE SNAPSHOT"
      )
    );
    const polling = candidate.polling;
    const campaign = candidate.campaign_attention;
    const general = candidate.general_visibility;
    const counts = campaign?.scope_counts;
    const shares = campaign?.scope_shares;

    section.append(
      snapshotRow(
        "Selected poll evidence",
        pollValue(candidate),
        hasValue(polling?.selected_hypothesis_score)
          ? Number(polling.selected_hypothesis_score)
          : null,
        "violet"
      ),
      snapshotRow(
        "Campaign/election visibility",
        campaign
          ? `${numberText(campaign.record_count)} records · ${percentageText(
            campaign.share,
            true
          )}`
          : MISSING,
        hasValue(campaign?.share) ? Number(campaign.share) * 100 : null
      ),
      snapshotRow(
        "General visibility",
        general
          ? `${numberText(general.record_count)} records · ${percentageText(
            general.share,
            true
          )}`
          : MISSING,
        hasValue(general?.share) ? Number(general.share) * 100 : null,
        "violet"
      ),
      snapshotRow(
        "Campaign composition",
        counts ? numberText(counts.campaign) : MISSING,
        hasValue(shares?.campaign) ? Number(shares.campaign) * 100 : null
      ),
      snapshotRow(
        "Election composition",
        counts ? numberText(counts.election) : MISSING,
        hasValue(shares?.election) ? Number(shares.election) * 100 : null,
        "violet"
      ),
      snapshotRow(
        "General composition",
        counts ? numberText(counts.general) : MISSING,
        hasValue(shares?.general) ? Number(shares.general) * 100 : null
      ),
      snapshotRow(
        "Publisher concentration",
        campaign?.concentration
          ? percentageText(
            campaign.concentration.leading_publisher_share,
            true
          )
          : MISSING,
        hasValue(campaign?.concentration?.leading_publisher_share)
          ? Number(campaign.concentration.leading_publisher_share) * 100
          : null,
        "violet"
      ),
      snapshotRow(
        "Claim scrutiny",
        candidate.scrutiny
          ? `BY ${numberText(candidate.scrutiny.archive?.by_count)} · ABOUT ${
            numberText(candidate.scrutiny.archive?.about_count)
          }`
          : MISSING
      )
    );
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
      evidenceLine("Published", development.published_at)
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

  function latestDevelopment(candidate, detailed = false) {
    const section = createElement(
      "section",
      detailed
        ? "candidate-signals-dossier-card candidate-signals-dossier-development"
        : "candidate-signals-latest-development"
    );
    section.append(
      createElement(
        "h3",
        detailed
          ? "candidate-signals-dossier-card-title"
          : "candidate-signals-subsection-title",
        "LATEST DEVELOPMENT"
      ),
      ...developmentContent(candidate, detailed)
    );
    return section;
  }

  function selectedAnalysis(candidate, metadata) {
    const section = createElement(
      "section",
      "candidate-signals-panel candidate-signals-analysis"
    );
    section.setAttribute("aria-labelledby", "candidate-signals-analysis-title");
    section.setAttribute("aria-live", "polite");
    section.setAttribute("aria-atomic", "true");

    const updateDate = metadata?.evidence_dates?.news;
    const header = regionHeader(
      "SELECTED ANALYSIS",
      hasValue(updateDate) ? `Published ${updateDate}` : null
    );
    header.querySelector("h2").id = "candidate-signals-analysis-title";

    const campaign = candidate.campaign_attention;
    const general = candidate.general_visibility;
    const counts = campaign?.scope_counts;
    const latest = candidate.scrutiny?.latest_14_days;
    const archive = candidate.scrutiny?.archive;
    const pollPackage = metadata?.featured_polling_package;

    const cards = createElement("div", "candidate-signals-analysis-cards");
    cards.append(
      analysisCard("POLL EVIDENCE", pollValue(candidate), [
        ["Pollster", pollPackage?.pollster || MISSING],
        ["Field dates", pollPackage && (
          hasValue(pollPackage.fieldwork_start) ||
          hasValue(pollPackage.fieldwork_end)
        )
          ? [pollPackage.fieldwork_start, pollPackage.fieldwork_end]
            .filter(hasValue)
            .join(" – ")
          : MISSING]
      ]),
      analysisCard(
        "CAMPAIGN ATTENTION",
        campaign ? `${numberText(campaign.record_count)} records` : MISSING,
        [
          ["Campaign/election", campaign
            ? percentageText(campaign.share, true)
            : MISSING],
          ["General", general
            ? `${numberText(general.record_count)} · ${percentageText(
              general.share,
              true
            )}`
            : MISSING]
        ]
      ),
      analysisCard(
        "COVERAGE COMPOSITION",
        counts ? "Published counts" : MISSING,
        compositionLines(candidate)
      ),
      analysisCard("SCRUTINY", "14 DAYS / ARCHIVE", [
        ["14 days", latest
          ? `BY ${numberText(latest.by_count)} · ABOUT ${numberText(
            latest.about_count
          )}`
          : MISSING],
        ["Archive", archive
          ? `BY ${numberText(archive.by_count)} · ABOUT ${numberText(
            archive.about_count
          )}`
          : MISSING]
      ])
    );

    const body = createElement("div", "candidate-signals-analysis-body");
    body.append(
      cards,
      evidenceSnapshot(candidate),
      latestDevelopment(candidate)
    );
    section.append(header, body);
    return section;
  }

  function dossierCard(title, groups, className = "") {
    const card = createElement(
      "section",
      `candidate-signals-dossier-card${className ? ` ${className}` : ""}`
    );
    card.append(
      createElement("h3", "candidate-signals-dossier-card-title", title)
    );
    groups.forEach(group => card.append(evidenceGroup(group[0], group[1])));
    return card;
  }

  function candidateDossier(candidate, metadata, options) {
    const section = createElement(
      "aside",
      "candidate-signals-panel candidate-signals-dossier"
    );
    section.setAttribute("aria-labelledby", "candidate-signals-dossier-title");
    const header = regionHeader("CANDIDATE DOSSIER");
    header.querySelector("h2").id = "candidate-signals-dossier-title";

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
        "h2",
        "candidate-signals-dossier-name",
        candidate.candidate_name
      )
    );
    identity.append(copy);

    const grid = createElement("div", "candidate-signals-dossier-grid");
    grid.append(
      dossierCard("POLL EVIDENCE", [["", pollLines(candidate, metadata)]]),
      dossierCard("VISIBILITY & COMPOSITION", [
        ["VISIBILITY", visibilityLines(candidate)],
        ["COMPOSITION", compositionLines(candidate)]
      ]),
      dossierCard(
        "EVIDENCE STRUCTURE",
        [
          [
            "CAMPAIGN / ELECTION",
            structureLines(candidate.campaign_attention, "Campaign/election")
          ],
          [
            "GENERAL",
            structureLines(candidate.general_visibility, "General")
          ]
        ],
        "candidate-signals-dossier-structure"
      ),
      dossierCard("CLAIM SCRUTINY", [["", scrutinyLines(candidate)]]),
      latestDevelopment(candidate, true)
    );
    body.append(identity, grid);
    section.append(header, body);
    return section;
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

    const candidates = Array.isArray(state.candidates)
      ? state.candidates
      : [];
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
      selectedAnalysis(selectedCandidate, state.metadata || {}),
      candidateDossier(selectedCandidate, state.metadata || {}, options)
    );
    mount.append(workspace);
    return selected;
  }

  window.France2027CandidateSignalsWorkspace = Object.freeze({
    render
  });
})();
