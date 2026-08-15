(() => {
  "use strict";

  let modal = null;
  let returnFocus = null;
  let candidates = [];
  let topics = [];
  let candidateProjectionAvailable = false;
  let candidateComparisonAvailable = false;
  let candidateComparisonReason = "";
  let publishers = [];
  let dailyActivity = [];
  let generatedAt = "";
  let latestPeriodLabel = "";
  let priorPeriodLabel = "";
  let highlightedCandidate = "";
  let highlightedTopic = "";

  const escapeHtml = value =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const escapeAttribute = escapeHtml;

  const numberOrZero = value => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };

  const parseTimestamp = value => {
    const parsed = new Date(value);
    return Number.isFinite(parsed.getTime())
      ? parsed
      : null;
  };

  const formatTimestamp = value => {
    const parsed = parseTimestamp(value);
    if (!parsed) return "Unavailable";

    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Europe/Paris"
    })
      .format(parsed)
      .replace(",", "");
  };

  const formatCompactDate = value => {
    const parsed = parseTimestamp(
      /^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))
        ? `${value}T00:00:00Z`
        : value
    );

    if (!parsed) return "—";

    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      timeZone: "UTC"
    }).format(parsed);
  };

  const formatWindowDate = value => {
    const parsed = parseTimestamp(value);
    if (!parsed) return "Unavailable";

    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC"
    }).format(parsed);
  };

  const deriveCoverageWindow = mediaModel => {
    const dated = (
      Array.isArray(mediaModel?.feedItems)
        ? mediaModel.feedItems
        : []
    )
      .map(item => parseTimestamp(item?.published_at))
      .filter(Boolean)
      .sort((a, b) => a.getTime() - b.getTime());

    if (!dated.length) {
      return {
        label: "Unavailable",
        days: 0
      };
    }

    const oldest = dated[0];
    const newest = dated[dated.length - 1];

    const oldestDay = Date.UTC(
      oldest.getUTCFullYear(),
      oldest.getUTCMonth(),
      oldest.getUTCDate()
    );
    const newestDay = Date.UTC(
      newest.getUTCFullYear(),
      newest.getUTCMonth(),
      newest.getUTCDate()
    );

    const days =
      Math.floor(
        (newestDay - oldestDay) /
        (24 * 60 * 60 * 1000)
      ) + 1;

    const oldestLabel = formatWindowDate(oldest);
    const newestLabel = formatWindowDate(newest);

    return {
      label:
        oldestLabel === newestLabel
          ? newestLabel
          : `${oldestLabel} – ${newestLabel}`,
      days
    };
  };

  const formatShare = value =>
    numberOrZero(value)
      .toFixed(1)
      .replace(/\.0$/, "");

  const formatDelta = value => {
    const amount = numberOrZero(value);
    return `${amount > 0 ? "+" : ""}${formatShare(amount)}pp`;
  };

  const deltaClass = value => {
    const amount = numberOrZero(value);
    if (amount > 0.05) return "is-up";
    if (amount < -0.05) return "is-down";
    return "is-flat";
  };

  const deltaArrow = value => {
    const amount = numberOrZero(value);
    if (amount > 0.05) return "▲";
    if (amount < -0.05) return "▼";
    return "—";
  };

  const isGeneralTopic = topic => {
    const identity = String(
      topic?.id || topic?.label || ""
    )
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();

    return (
      identity.startsWith("other ") ||
      identity.includes("other campaign coverage")
    );
  };

  const normalizeCandidate = item => {
    const latestShare =
      item?.latestShare === null
        ? null
        : Number.isFinite(Number(item?.latestShare))
          ? Number(item.latestShare)
          : null;
    const previousShare =
      item?.previousShare === null
        ? null
        : Number.isFinite(Number(item?.previousShare))
          ? Number(item.previousShare)
          : null;
    const delta =
      item?.delta === null
        ? null
        : Number.isFinite(Number(item?.delta))
          ? Number(item.delta)
          : null;
    const changeAvailable =
      candidateComparisonAvailable &&
      item?.changeAvailable === true &&
      delta !== null;
    const tier = String(item?.tier || "");

    return {
      id: String(item?.id || ""),
      name: String(item?.name || "Unknown candidate").trim() ||
        "Unknown candidate",
      tier,
      tierLabel: String(
        item?.tierLabel ||
        (
          tier === "main"
            ? "MAIN FIELD"
            : tier === "secondary"
              ? "SECONDARY FIELD"
              : ""
        )
      ),
      status: String(item?.status || ""),
      latestShare,
      previousShare,
      latestCount: numberOrZero(item?.latestCount),
      previousCount: numberOrZero(item?.previousCount),
      changeAvailable,
      delta: changeAvailable ? delta : null
    };
  };

  const normalizeTopic = item => ({
    id: String(item?.id || item?.label || ""),
    label:
      String(item?.label || "Untitled topic").trim() ||
      "Untitled topic",
    sourceDays: numberOrZero(item?.source_day_count),
    itemCount: numberOrZero(item?.item_count),
    publisherCount: numberOrZero(item?.publisher_count),
    activeDayCount: numberOrZero(item?.active_day_count)
  });

  const normalizePublisher = item => ({
    name:
      String(item?.name || "Unknown publisher").trim() ||
      "Unknown publisher",
    count: numberOrZero(item?.count)
  });

  const normalizeDay = item => ({
    key: String(item?.key || ""),
    count: numberOrZero(item?.count)
  });

  const renderMetric = (
    value,
    label,
    note = "",
    className = ""
  ) => `
    <div class="tcm-summary-metric${className ? ` ${className}` : ""}">
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(label)}</span>
      ${note ? `<small>${escapeHtml(note)}</small>` : ""}
    </div>
  `;

  const renderSummaryStrip = mediaModel => {
    const coverageWindow =
      deriveCoverageWindow(mediaModel);

    return `
      <section
        class="tcm-summary-strip"
        aria-label="Coverage summary"
      >
        ${renderMetric(
          String(numberOrZero(mediaModel?.electionNewsCount)),
          "Accepted news"
        )}
        ${renderMetric(
          String(numberOrZero(mediaModel?.acceptedNewsPublisherCount)),
          "Publishers"
        )}
        ${renderMetric(
          String(numberOrZero(mediaModel?.activityItemCount)),
          "Recent activity",
          `${numberOrZero(mediaModel?.activityWindowDays)} days`
        )}
        ${renderMetric(
          coverageWindow.label,
          "Coverage window",
          coverageWindow.days
            ? `${coverageWindow.days} days`
            : "Current record range",
          "is-window"
        )}
      </section>
    `;
  };

  const candidateComparisonLabel = () =>
    candidateComparisonAvailable
      ? "Δ pp"
      : candidateProjectionAvailable
        ? "RAW Δ pp"
        : "UNAVAILABLE";

  const renderPeriodLegend = () => {
    const reasonLabel =
      candidateComparisonReason ===
      "publisher_panel_changed"
        ? "publisher panel changed"
        : candidateComparisonReason ===
          "insufficient_data"
          ? "insufficient data"
          : "comparison unavailable";
    const qualityExplanation =
      candidateComparisonAvailable
        ? "Comparable active-field percentage-point change."
        : candidateProjectionAvailable
          ? `Comparison quality is not comparable: ${reasonLabel}. Raw arithmetic differences are current-minus-prior percentage-point values, not comparable trend estimates.`
          : "Active-field candidate comparison unavailable.";

    return `
      <div
        class="tcm-period-legend"
        role="group"
        aria-label="${escapeAttribute(
          `Active-field candidate-linked share. Current period ${latestPeriodLabel}; prior period ${priorPeriodLabel}. ${qualityExplanation}`
        )}"
      >
        <span>
          <i class="is-current" aria-hidden="true"></i>
          <strong>CURRENT</strong>
          <small>${escapeHtml(latestPeriodLabel)}</small>
        </span>
        <span>
          <i class="is-prior" aria-hidden="true"></i>
          <strong>PRIOR</strong>
          <small>${escapeHtml(priorPeriodLabel)}</small>
        </span>
      </div>
    `;
  };

  const renderCoverageShiftRows = () => {
    if (!candidateProjectionAvailable) {
      return `
        <div class="tcm-empty">
          Active-field candidate comparison unavailable.
        </div>
      `;
    }
    const maximum = Math.max(
      1,
      ...candidates.map(item =>
        numberOrZero(item.latestShare) + numberOrZero(item.previousShare)
      )
    );
    const renderGroup = (tier, label) => {
      const rows = candidates.filter(item => item.tier === tier);
      const renderedRows = rows.map(item => {
        const currentWidth = Math.min(
          100,
          numberOrZero(item.latestShare) / maximum * 100
        );
        const priorWidth = Math.min(
          100,
          numberOrZero(item.previousShare) / maximum * 100
        );
        const highlighted = item.name === highlightedCandidate
          ? " is-highlighted"
          : "";
        const latestText = item.latestShare === null
          ? "—"
          : `${formatShare(item.latestShare)}%`;
        const priorText = item.previousShare === null
          ? "—"
          : `${formatShare(item.previousShare)}%`;
        const rawDeltaAvailable =
          !item.changeAvailable &&
          Number.isFinite(item.latestShare) &&
          Number.isFinite(item.previousShare);
        const displayedDelta =
          item.changeAvailable
            ? item.delta
            : rawDeltaAvailable
              ? item.latestShare - item.previousShare
              : null;
        const deltaMarkup =
          displayedDelta === null
            ? "—"
            : item.changeAvailable
              ? `${deltaArrow(item.delta)} ${formatDelta(item.delta)}`
              : `${deltaArrow(displayedDelta)} ${formatDelta(displayedDelta)}`;
        return `
          <div
            class="tcm-shift-row${displayedDelta === null ? " is-limited" : ""}${highlighted}"
            data-tcm-candidate-row="${escapeAttribute(item.name)}"
            title="${escapeAttribute(item.name)}"
            aria-label="${escapeAttribute(
              `${item.name}. Candidate status ${item.status}. Current active-field share ${latestText}; prior active-field share ${priorText}.${item.changeAvailable ? ` Comparable change ${deltaMarkup}.` : rawDeltaAvailable ? ` Raw arithmetic difference ${deltaMarkup}. Publisher panels changed, so this is not a comparable trend estimate.` : ""}`
            )}"
          >
            <strong title="${escapeAttribute(item.name)}">${escapeHtml(item.name)}</strong>
            <b>${escapeHtml(latestText)}</b>
            <span class="tcm-shift-track" aria-hidden="true">
              <i class="is-current" style="--tcm-current-width:${currentWidth.toFixed(2)}%"></i>
              <i class="is-prior" style="--tcm-prior-width:${priorWidth.toFixed(2)}%"></i>
            </span>
            <em>${escapeHtml(priorText)}</em>
            <span class="tcm-delta ${displayedDelta === null ? "is-limited" : deltaClass(displayedDelta)}">
              ${escapeHtml(deltaMarkup)}
            </span>
          </div>
        `;
      }).join("");
      return `
        <div class="tcm-module-head">
          <h3>${escapeHtml(label)}</h3>
          <span>${rows.length} active candidates</span>
        </div>
        ${renderedRows}
      `;
    };
    return renderGroup("main", "MAIN FIELD") +
      renderGroup("secondary", "SECONDARY FIELD");
  };

  const renderTopicRows = () => {
    if (!topics.length) {
      return `
        <div class="tcm-empty">
          Recurring topic data unavailable.
        </div>
      `;
    }

    const maximum = Math.max(
      1,
      ...topics.map(item => item.sourceDays)
    );

    return topics
      .map((item, index) => {
        const width = Math.min(
          100,
          item.sourceDays / maximum * 100
        );
        const highlighted =
          item.id === highlightedTopic
            ? " is-highlighted"
            : "";

        return `
          <div
            class="tcm-topic-item${highlighted}"
            data-tcm-topic-row="${escapeAttribute(item.id)}"
          >
            <span class="tcm-rank">
              ${String(index + 1).padStart(2, "0")}
            </span>
            <span class="tcm-row-copy">
              <strong>${escapeHtml(item.label)}</strong>
              <small>
                ${item.itemCount} items ·
                ${item.publisherCount} publishers ·
                ${item.activeDayCount} active days
              </small>
              <i class="tcm-topic-track" aria-hidden="true">
                <b
                  style="--tcm-topic-width:${width.toFixed(2)}%"
                ></b>
              </i>
            </span>
            <b>${item.sourceDays}</b>
          </div>
        `;
      })
      .join("");
  };

  const renderPublisherRows = () => {
    if (!publishers.length) {
      return `
        <div class="tcm-empty">
          Publisher ranking unavailable.
        </div>
      `;
    }

    const maximum = Math.max(
      1,
      ...publishers.map(item => item.count)
    );

    return publishers
      .map((item, index) => {
        const width = Math.min(
          100,
          item.count / maximum * 100
        );

        return `
          <div class="tcm-publisher-item">
            <span class="tcm-rank">
              ${String(index + 1).padStart(2, "0")}
            </span>
            <strong>${escapeHtml(item.name)}</strong>
            <i class="tcm-publisher-track" aria-hidden="true">
              <b
                style="--tcm-publisher-width:${width.toFixed(2)}%"
              ></b>
            </i>
            <b>${item.count}</b>
          </div>
        `;
      })
      .join("");
  };

  const formatVolumeDay = value => {
    const parsed = parseTimestamp(
      /^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))
        ? `${value}T00:00:00Z`
        : value
    );

    if (!parsed) return "—";

    return new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      timeZone: "UTC"
    }).format(parsed);
  };

  const renderDailyVolumeMeta = () => {
    if (!dailyActivity.length) {
      return "Accepted reports per day";
    }

    const firstLabel = formatCompactDate(
      dailyActivity[0].key
    );
    const lastLabel = formatCompactDate(
      dailyActivity[dailyActivity.length - 1].key
    );
    const firstParts = firstLabel.split(" ");
    const lastParts = lastLabel.split(" ");
    const range =
      firstParts.length === 2 &&
      lastParts.length === 2 &&
      firstParts[1] === lastParts[1]
        ? `${firstParts[0]}–${lastLabel}`
        : `${firstLabel}–${lastLabel}`;
    const total = dailyActivity.reduce(
      (sum, item) => sum + item.count,
      0
    );

    return `${range} · total ${total}`;
  };

  const renderDailyVolume = () => {
    if (!dailyActivity.length) {
      return `
        <div class="tcm-empty">
          Daily activity data unavailable.
        </div>
      `;
    }

    const maximum = Math.max(
      1,
      ...dailyActivity.map(item => item.count)
    );

    const bars = dailyActivity
      .map(item => {
        const height = Math.max(
          item.count ? 7 : 2,
          item.count / maximum * 100
        );

        return `
          <div
            class="tcm-volume-day"
            aria-label="${escapeAttribute(
              `${formatCompactDate(item.key)}: ${item.count} accepted reports`
            )}"
          >
            <b>${item.count}</b>
            <i aria-hidden="true">
              <span
                style="--tcm-volume-height:${height.toFixed(2)}%"
              ></span>
            </i>
            <time datetime="${escapeAttribute(item.key)}">
              ${escapeHtml(formatVolumeDay(item.key))}
            </time>
          </div>
        `;
      })
      .join("");

    return `
      <div
        class="tcm-volume-wrap"
        role="img"
        aria-label="Daily accepted election coverage"
      >
        <div class="tcm-volume-chart">
          ${bars}
        </div>
      </div>
    `;
  };

  const renderModule = (
    className,
    title,
    meta,
    content
  ) => `
    <section class="tcm-module ${className}">
      <header class="tcm-module-head">
        <h3>${escapeHtml(title)}</h3>
        ${meta ? `<span>${escapeHtml(meta)}</span>` : ""}
      </header>
      <div class="tcm-module-body">
        ${content}
      </div>
    </section>
  `;

  const renderBody = mediaModel => `
    <div class="tcm-shell">
      ${renderSummaryStrip(mediaModel)}
      <div class="tcm-intelligence-grid">
        ${renderModule(
          "tcm-module-shift",
          "Active-field coverage shift",
          candidateComparisonLabel(),
          renderPeriodLegend() +
            `<div
              class="tcm-shift-list tcm-scroll-y"
              tabindex="0"
              aria-label="Complete active-field candidate coverage shift"
            >${renderCoverageShiftRows()}</div>`
        )}
        ${renderModule(
          "tcm-module-topics",
          "Topic coverage",
          "Source-days · 30-day context",
          `<div
            class="tcm-topic-list tcm-scroll-y"
            tabindex="0"
            aria-label="Complete recurring topic ranking"
          >${renderTopicRows()}</div>`
        )}
        ${renderModule(
          "tcm-module-publishers",
          "Top publishers",
          `${publishers.length} represented`,
          `<div
            class="tcm-publisher-list tcm-scroll-y"
            tabindex="0"
            aria-label="Complete publisher ranking"
          >${renderPublisherRows()}</div>`
        )}
        ${renderModule(
          "tcm-module-volume",
          "Daily volume",
          renderDailyVolumeMeta(),
          renderDailyVolume()
        )}
      </div>
    </div>
  `;

  const focusableElements = () =>
    modal
      ? [
          ...modal.querySelectorAll(
            [
              "a[href]",
              "button:not([disabled])",
              "input:not([disabled])",
              "select:not([disabled])",
              '[tabindex]:not([tabindex="-1"])'
            ].join(",")
          )
        ].filter(
          element =>
            !element.hasAttribute("hidden") &&
            element.getAttribute("aria-hidden") !== "true"
        )
      : [];

  const close = () => {
    if (!modal || modal.hidden) return;

    modal.hidden = true;
    document.body.classList.remove("tcm-is-open");

    if (
      returnFocus &&
      document.contains(returnFocus)
    ) {
      returnFocus.setAttribute("aria-expanded", "false");
      returnFocus.focus();
    }

    returnFocus = null;
  };

  const ensureModal = () => {
    if (modal) return modal;

    document.body.insertAdjacentHTML(
      "beforeend",
      `
        <div
          class="tcm-overlay"
          id="topic-coverage-modal"
          hidden
        >
          <section
            class="tcm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tcm-title"
          >
            <header class="tcm-header">
              <h2 id="tcm-title">
                Media Pulse / Coverage Analysis
              </h2>
              <div class="tcm-header-actions">
                <span
                  class="tcm-updated"
                  data-tcm-updated
                ></span>
                <button
                  class="tcm-close"
                  type="button"
                  aria-label="Close coverage analysis"
                  data-tcm-close
                >×</button>
              </div>
            </header>
            <div
              class="tcm-body"
              data-tcm-body
            ></div>
          </section>
        </div>
      `
    );

    modal = document.getElementById(
      "topic-coverage-modal"
    );

    modal.addEventListener("click", event => {
      if (
        event.target === modal ||
        event.target.closest("[data-tcm-close]")
      ) {
        close();
      }
    });

    modal.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }

      if (event.key !== "Tab") return;

      const focusable = focusableElements();
      if (!focusable.length) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (
        event.shiftKey &&
        document.activeElement === first
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        document.activeElement === last
      ) {
        event.preventDefault();
        first.focus();
      }
    });

    return modal;
  };

  const reconcileReturnFocus = () => {
    if (
      !returnFocus ||
      document.contains(returnFocus)
    ) {
      return;
    }

    const attributes = [
      "data-topic-coverage-open",
      "data-hybrid-media-topic",
      "data-hybrid-media-candidate"
    ];

    const attribute = attributes.find(name =>
      returnFocus.hasAttribute(name)
    );

    if (!attribute) {
      returnFocus = null;
      return;
    }

    const value = returnFocus.getAttribute(attribute);

    returnFocus = [
      ...document.querySelectorAll(`[${attribute}]`)
    ].find(
      element =>
        element.getAttribute(attribute) === value
    ) || null;
  };

  const open = (
    models,
    trigger = null,
    options = {}
  ) => {
    const mediaModel = models?.media || {};
    const agendaModel = models?.agenda || {};

    candidateProjectionAvailable =
      mediaModel.candidateCoverageAvailable === true &&
      Array.isArray(mediaModel.candidateCoverage);
    candidateComparisonAvailable =
      mediaModel.comparisonQuality?.status === "comparable";
    candidateComparisonReason = String(
      mediaModel.comparisonQuality?.reason || ""
    );
    candidates = candidateProjectionAvailable
      ? mediaModel.candidateCoverage.map(normalizeCandidate)
      : [];

    topics = Array.isArray(agendaModel?.topics)
      ? agendaModel.topics
          .filter(item => item?.display_eligible)
          .filter(item => !isGeneralTopic(item))
          .map(normalizeTopic)
          .sort(
            (a, b) =>
              b.sourceDays - a.sourceDays ||
              b.publisherCount - a.publisherCount ||
              a.label.localeCompare(b.label, "en")
          )
      : [];

    publishers = Array.isArray(
      mediaModel.publisherRanking
    )
      ? mediaModel.publisherRanking
          .map(normalizePublisher)
          .filter(item => item.name)
      : Array.isArray(mediaModel.topPublishers)
        ? mediaModel.topPublishers
            .map(normalizePublisher)
            .filter(item => item.name)
        : [];

    dailyActivity = Array.isArray(
      mediaModel.dailyActivity
    )
      ? mediaModel.dailyActivity
          .map(normalizeDay)
          .filter(item => item.key)
      : [];

    if (
      !candidates.length &&
      !topics.length &&
      !publishers.length &&
      !dailyActivity.length
    ) {
      return;
    }

    highlightedCandidate = String(
      options?.candidateName || ""
    );
    highlightedTopic = String(
      options?.topicId || ""
    );
    latestPeriodLabel = String(
      mediaModel.latestPeriodLabel || ""
    );
    priorPeriodLabel = String(
      mediaModel.priorPeriodLabel || ""
    );
    generatedAt = String(
      mediaModel.generatedAt ||
      agendaModel.generatedAt ||
      ""
    );

    ensureModal();
    returnFocus = trigger;

    if (
      returnFocus &&
      document.contains(returnFocus)
    ) {
      returnFocus.setAttribute(
        "aria-expanded",
        "true"
      );
    }

    modal.querySelector(
      "[data-tcm-updated]"
    ).textContent =
      `Updated: ${formatTimestamp(generatedAt)}`;

    modal.querySelector(
      "[data-tcm-body]"
    ).innerHTML = renderBody(mediaModel);

    modal.hidden = false;
    document.body.classList.add("tcm-is-open");

    requestAnimationFrame(() => {
      modal.querySelector("[data-tcm-close]")?.focus();

      const highlighted =
        modal.querySelector(
          ".tcm-shift-row.is-highlighted"
        ) ||
        modal.querySelector(
          ".tcm-topic-item.is-highlighted"
        );

      highlighted?.scrollIntoView({
        block: "nearest"
      });
    });
  };

  window.France2027TopicCoverageModal = {
    open,
    close,
    reconcileReturnFocus
  };
})();
