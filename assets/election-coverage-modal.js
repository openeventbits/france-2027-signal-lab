(() => {
  "use strict";

  let modal = null;
  let returnFocus = null;
  let records = [];
  let contextTopics = [];
  let topicContextDays = 0;
  let modelTopPublishers = [];
  let candidateCoverageLeaders = [];
  let comparisonQuality = {};
  let latestPeriodLabel = "";
  let priorPeriodLabel = "";
  let dailyActivity = [];
  let activityMax = 1;

  const state = {
    query: "",
    publisher: "",
    candidate: "",
    sort: "newest",
    activeTab: "coverage"
  };

  const collator = new Intl.Collator(
    "fr",
    {
      sensitivity: "base"
    }
  );

  const escapeHtml = value =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const escapeAttribute = escapeHtml;

  const normalizeSearch = value =>
    String(value ?? "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();

  const safeUrl = value => {
    try {
      const parsed = new URL(
        String(value || ""),
        window.location.href
      );

      return ["http:", "https:"].includes(
        parsed.protocol
      )
        ? parsed.href
        : "";
    } catch {
      return "";
    }
  };

  const parseTimestamp = value => {
    const parsed = new Date(value);

    return Number.isFinite(parsed.getTime())
      ? parsed
      : null;
  };

  const formatRecordDay = value => {
    const parsed = parseTimestamp(value);

    if (!parsed) return "Date unavailable";

    return new Intl.DateTimeFormat(
      "en-GB",
      {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "Europe/Paris"
      }
    ).format(parsed);
  };

  const formatRecordTime = value => {
    const parsed = parseTimestamp(value);

    if (!parsed) return "";

    return new Intl.DateTimeFormat(
      "en-GB",
      {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "Europe/Paris"
      }
    ).format(parsed);
  };

  const formatTimestamp = value => {
    const parsed = parseTimestamp(value);

    if (!parsed) return "Unavailable";

    return new Intl.DateTimeFormat(
      "en-GB",
      {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "Europe/Paris"
      }
    )
      .format(parsed)
      .replace(",", "");
  };

  const numberValue = value => {
    const parsed = Number(value);

    return Number.isFinite(parsed)
      ? parsed
      : 0;
  };

  const formatShare = value => {
    const parsed = numberValue(value);

    const normalized =
      Math.abs(parsed) < 0.05
        ? 0
        : parsed;

    return Number.isInteger(normalized)
      ? String(normalized)
      : normalized
          .toFixed(1)
          .replace(/\.0$/, "");
  };

  const formatActivityDay = item => {
    const source =
      item?.date ||
      (
        item?.key
          ? `${item.key}T00:00:00Z`
          : ""
      );

    const parsed = new Date(source);

    if (!Number.isFinite(parsed.getTime())) {
      return "—";
    }

    return new Intl.DateTimeFormat(
      "en-GB",
      {
        day: "2-digit",
        month: "short",
        timeZone: "UTC"
      }
    )
      .format(parsed)
      .toUpperCase();
  };

  const candidateNames = item => {
    const source = Array.isArray(
      item?.candidate_names
    )
      ? item.candidate_names
      : [];

    return [
      ...new Set(
        source
          .map(value => String(value || "").trim())
          .filter(Boolean)
      )
    ];
  };

  const normalizeRecords = model =>
    model.feedItems.map(
      (item, index) => {
        const publishedAt = String(
          item?.published_at || ""
        );

        const parsed =
          parseTimestamp(publishedAt);

        const publisher =
          String(
            item?.publisher ||
            "Unknown publisher"
          ).trim() ||
          "Unknown publisher";

        const headline =
          String(
            item?.headline ||
            "Untitled coverage record"
          ).trim() ||
          "Untitled coverage record";

        const candidates =
          candidateNames(item);

        return {
          index,
          publishedAt,
          timestamp:
            parsed
              ? parsed.getTime()
              : 0,
          publisher,
          headline,
          candidates,
          url: String(item?.url || ""),
          searchText:
            normalizeSearch(
              [
                headline,
                publisher,
                ...candidates
              ].join(" ")
            )
        };
      }
    );

  const uniqueSorted = values =>
    [
      ...new Set(
        values
          .map(value =>
            String(value || "").trim()
          )
          .filter(Boolean)
      )
    ].sort((a, b) =>
      collator.compare(a, b)
    );

  const optionMarkup = values =>
    values
      .map(
        value => `
          <option value="${escapeAttribute(value)}">
            ${escapeHtml(value)}
          </option>
        `
      )
      .join("");

  const renderTags = record => {
    if (!record.candidates.length) {
      return "";
    }

    return `
      <div
        class="ecm-feed-tags"
        aria-label="Associated candidates"
      >
        ${record.candidates
          .slice(0, 3)
          .map(
            candidate => `
              <span>
                ${escapeHtml(candidate)}
              </span>
            `
          )
          .join("")}
      </div>
    `;
  };

  const renderSource = record => {
    const href = safeUrl(record.url);

    if (!href) {
      return `
        <span class="ecm-source-unavailable">
          Source unavailable
        </span>
      `;
    }

    return `
      <a
        class="ecm-feed-source"
        href="${escapeAttribute(href)}"
        target="_blank"
        rel="noopener noreferrer"
      >
        Open source
        <span aria-hidden="true">↗</span>
      </a>
    `;
  };

  const renderFeedRow = record => `
    <article class="ecm-feed-row">
      <time
        class="ecm-feed-time"
        datetime="${escapeAttribute(
          record.publishedAt
        )}"
      >
        <span>
          ${escapeHtml(
            formatRecordDay(
              record.publishedAt
            )
          )}
        </span>

        ${
          formatRecordTime(
            record.publishedAt
          )
            ? `
              <small>
                ${escapeHtml(
                  formatRecordTime(
                    record.publishedAt
                  )
                )}
              </small>
            `
            : ""
        }
      </time>

      <div class="ecm-feed-publisher">
        ${escapeHtml(record.publisher)}
      </div>

      <div class="ecm-feed-copy">
        <h4 lang="fr">
          ${escapeHtml(record.headline)}
        </h4>

        ${renderTags(record)}
      </div>

      <div class="ecm-feed-action">
        ${renderSource(record)}
      </div>
    </article>
  `;

  const filteredRecords = () => {
    const query =
      normalizeSearch(state.query);

    const selected = records.filter(
      record => {
        if (
          query &&
          !record.searchText.includes(query)
        ) {
          return false;
        }

        if (
          state.publisher &&
          record.publisher !== state.publisher
        ) {
          return false;
        }

        if (
          state.candidate &&
          !record.candidates.includes(
            state.candidate
          )
        ) {
          return false;
        }

        return true;
      }
    );

    const direction =
      state.sort === "oldest"
        ? 1
        : -1;

    return selected.sort(
      (a, b) =>
        (a.timestamp - b.timestamp) *
          direction ||
        a.index - b.index
    );
  };

  const resultLabel = count => {
    const noun =
      records.length === 1
        ? "record"
        : "records";

    return (
      `${count} of ${records.length} ` +
      `recent ${noun}`
    );
  };

  const updateFeed = () => {
    const list = modal?.querySelector(
      "[data-ecm-feed-list]"
    );

    const summary = modal?.querySelector(
      "[data-ecm-result-summary]"
    );

    if (!list || !summary) return;

    const selected =
      filteredRecords();

    summary.textContent =
      resultLabel(selected.length);

    list.innerHTML =
      selected.length
        ? selected
            .map(renderFeedRow)
            .join("")
        : `
          <div
            class="ecm-empty"
            role="status"
          >
            <strong>No matching coverage</strong>
            <span>
              Adjust the search or filters to
              show recent records.
            </span>
          </div>
        `;
  };

  const publisherCounts = () => {
    const counts = new Map();

    records.forEach(record => {
      counts.set(
        record.publisher,
        (counts.get(record.publisher) || 0) +
          1
      );
    });

    return [
      ...counts.entries()
    ]
      .map(([name, count]) => ({
        name,
        count
      }))
      .sort(
        (a, b) =>
          b.count - a.count ||
          collator.compare(a.name, b.name)
      );
  };

  const latestRecord = () =>
    records.reduce(
      (latest, record) =>
        !latest ||
        record.timestamp > latest.timestamp
          ? record
          : latest,
      null
    );

  const renderPublisherRows = () => {
    const fallbackPublishers =
      publisherCounts();

    const publishers =
      modelTopPublishers.length
        ? modelTopPublishers
        : fallbackPublishers;

    if (!publishers.length) {
      return `
        <p class="ecm-snapshot-empty">
          Publisher data unavailable.
        </p>
      `;
    }

    const maximum = Math.max(
      1,
      ...publishers.map(
        publisher =>
          numberValue(publisher.count)
      )
    );

    return publishers
      .map(
        (publisher, index) => {
          const count =
            numberValue(publisher.count);

          const width =
            count / maximum * 100;

          return `
            <div class="ecm-publisher-row">
              <span class="ecm-rank">
                ${index + 1}
              </span>

              <strong
                title="${escapeAttribute(
                  publisher.name
                )}"
              >
                ${escapeHtml(publisher.name)}
              </strong>

              <i aria-hidden="true">
                <b
                  style="--ecm-publisher-width:${width.toFixed(2)}%"
                ></b>
              </i>

              <em>${count}</em>
            </div>
          `;
        }
      )
      .join("");
  };

  const latest24HourCount = () => {
    const timestamps = records
      .map(record => record.timestamp)
      .filter(timestamp => timestamp > 0);

    if (!timestamps.length) return 0;

    const newest = Math.max(...timestamps);
    const oneDay = 24 * 60 * 60 * 1000;

    return timestamps.filter(
      timestamp =>
        newest - timestamp <= oneDay
    ).length;
  };

  const coverageWindowLabel = () => {
    const dated = records
      .filter(record => record.timestamp > 0)
      .sort(
        (a, b) =>
          a.timestamp - b.timestamp
      );

    if (!dated.length) {
      return "Unavailable";
    }

    const oldest = dated[0];
    const newest = dated[dated.length - 1];

    const oldestLabel =
      formatRecordDay(oldest.publishedAt);

    const newestLabel =
      formatRecordDay(newest.publishedAt);

    return oldestLabel === newestLabel
      ? newestLabel
      : `${oldestLabel}–${newestLabel}`;
  };

  const coverageWindowDays = () => {
    const timestamps = records
      .map(record => record.timestamp)
      .filter(timestamp => timestamp > 0);

    if (!timestamps.length) return 0;

    const oldest = Math.min(...timestamps);
    const newest = Math.max(...timestamps);
    const oneDay = 24 * 60 * 60 * 1000;

    return Math.max(
      1,
      Math.floor(
        (newest - oldest) / oneDay
      ) + 1
    );
  };

  const renderContextTopics = () => {
    if (!contextTopics.length) {
      return `
        <p class="ecm-snapshot-empty">
          Topic context unavailable.
        </p>
      `;
    }

    const topics =
      [...contextTopics];

    const maximum = Math.max(
      1,
      ...topics.map(
        topic => numberValue(topic.metric)
      )
    );

    return topics
      .map(
        (topic, index) => {
          const metric =
            numberValue(topic.metric);

          const width =
            metric / maximum * 100;

          return `
            <div class="ecm-topic-row">
              <span class="ecm-rank">
                ${index + 1}
              </span>

              <strong
                title="${escapeAttribute(
                  topic.label
                )}"
              >
                ${escapeHtml(topic.label)}
              </strong>

              <i aria-hidden="true">
                <b
                  style="--ecm-topic-width:${width.toFixed(2)}%"
                ></b>
              </i>

              <em>${metric}</em>
            </div>
          `;
        }
      )
      .join("");
  };

  const renderCoverageMetrics = () => {
    const publishers =
      publisherCounts();

    return `
      <section
        class="ecm-metric-strip"
        aria-label="Coverage summary"
      >
        <div>
          <span>Recent records</span>
          <strong>${records.length}</strong>
          <small>of ${records.length}</small>
        </div>

        <div>
          <span>Publishers</span>
          <strong>${publishers.length}</strong>
          <small>represented</small>
        </div>

        <div>
          <span>Latest 24h</span>
          <strong>${latest24HourCount()}</strong>
          <small>records</small>
        </div>

        <div class="is-window">
          <span>Coverage window</span>
          <strong>
            ${escapeHtml(
              coverageWindowLabel()
            )}
          </strong>
          <small>
            ${coverageWindowDays() === 1
              ? "1 day"
              : `${coverageWindowDays()} days`}
          </small>
        </div>
      </section>
    `;
  };

  const renderCoverageShiftRows = () => {
    const leaders =
      [...candidateCoverageLeaders];

    if (!leaders.length) {
      return `
        <p class="ecm-snapshot-empty">
          Candidate coverage data unavailable.
        </p>
      `;
    }

    const maximum = Math.max(
      1,
      ...leaders.map(
        item =>
          numberValue(item.latestShare) +
          numberValue(item.previousShare)
      )
    );

    return leaders
      .map(item => {
        const current =
          numberValue(item.latestShare);

        const prior =
          numberValue(item.previousShare);

        const parsedDelta =
          Number(item.delta);

        const comparable =
          item.changeAvailable === true &&
          Number.isFinite(parsedDelta);

        const delta =
          comparable
            ? parsedDelta
            : current - prior;

        const direction =
          delta > 0.05
            ? "▲"
            : delta < -0.05
              ? "▼"
              : "—";

        const directionClass =
          delta > 0.05
            ? "is-up"
            : delta < -0.05
              ? "is-down"
              : "is-flat";

        const currentWidth =
          current / maximum * 100;

        const priorWidth =
          prior / maximum * 100;

        const deltaText =
          `${delta > 0 ? "+" : ""}` +
          `${formatShare(delta)}pp`;

        return `
          <div
            class="ecm-shift-row"
            title="${escapeAttribute(
              comparable
                ? "Comparable percentage-point change."
                : "Raw period difference only; publisher mix is not comparable."
            )}"
          >
            <span>
              ${escapeHtml(item.name)}
            </span>

            <strong>
              ${formatShare(current)}%
            </strong>

            <i aria-hidden="true">
              <b
                class="is-current"
                style="--ecm-current-width:${currentWidth.toFixed(2)}%"
              ></b>

              <b
                class="is-prior"
                style="--ecm-prior-width:${priorWidth.toFixed(2)}%"
              ></b>
            </i>

            <em>
              ${formatShare(prior)}%
            </em>

            <b
              class="ecm-shift-delta ${directionClass} ${
                comparable
                  ? ""
                  : "is-limited"
              }"
            >
              ${direction}
              ${comparable ? "" : "≈ "}
              ${escapeHtml(deltaText)}
            </b>
          </div>
        `;
      })
      .join("");
  };

  const renderDailyVolume = () => {
    const days =
      dailyActivity.slice(-7);

    if (!days.length) {
      return `
        <p class="ecm-snapshot-empty">
          Daily activity unavailable.
        </p>
      `;
    }

    const maximum = Math.max(
      1,
      activityMax,
      ...days.map(
        day => numberValue(day.count)
      )
    );

    const total = days.reduce(
      (sum, day) =>
        sum + numberValue(day.count),
      0
    );

    return `
      <div
        class="ecm-volume-chart"
        role="img"
        aria-label="${escapeAttribute(
          `${total} accepted election-news records across the displayed seven-day period.`
        )}"
      >
        ${days
          .map(day => {
            const count =
              numberValue(day.count);

            const height =
              count / maximum * 100;

            return `
              <div
                class="ecm-volume-day"
                title="${escapeAttribute(
                  `${formatActivityDay(day)}: ${count} records`
                )}"
              >
                <span aria-hidden="true">
                  <i
                    style="--ecm-volume-height:${height.toFixed(2)}%"
                  ></i>
                </span>

                <b>${formatActivityDay(day)}</b>
                <strong>${count}</strong>
              </div>
            `;
          })
          .join("")}
      </div>
    `;
  };

  const renderIntelligence = () => {
    const comparisonLabel =
      comparisonQuality?.status ===
      "comparable"
        ? "Δ PP"
        : "RAW Δ PP";

    const dailyTotal =
      dailyActivity
        .slice(-7)
        .reduce(
          (sum, day) =>
            sum + numberValue(day.count),
          0
        );

    return `
      <div class="ecm-intelligence-tab">
        ${renderCoverageMetrics()}

        <div class="ecm-intelligence-grid">
          <section
            class="ecm-module ecm-shift-module"
            aria-labelledby="ecm-shift-title"
          >
            <header>
              <h3 id="ecm-shift-title">
                Coverage shift
              </h3>
              <span>${comparisonLabel}</span>
            </header>

            <div class="ecm-shift-legend">
              <span class="is-current">
                <i></i>
                CURRENT
                <small>
                  ${escapeHtml(
                    latestPeriodLabel ||
                    "Current"
                  )}
                </small>
              </span>

              <span class="is-prior">
                <i></i>
                PRIOR
                <small>
                  ${escapeHtml(
                    priorPeriodLabel ||
                    "Prior"
                  )}
                </small>
              </span>
            </div>

            <div
              class="ecm-shift-list ecm-module-scroll"
              role="region"
              aria-label="Complete candidate coverage shift ranking"
              tabindex="0"
            >
              ${renderCoverageShiftRows()}
            </div>
          </section>

          <section
            class="ecm-module ecm-topic-module"
            aria-labelledby="ecm-topic-title"
          >
            <header>
              <h3 id="ecm-topic-title">
                Topic coverage
              </h3>
              <span>
                Source-days
                ${topicContextDays > 0
                  ? ` · ${topicContextDays}-day context`
                  : ""}
              </span>
            </header>

            <div
              class="ecm-module-body ecm-module-scroll"
              role="region"
              aria-label="Complete topic coverage ranking"
              tabindex="0"
            >
              ${renderContextTopics()}
            </div>
          </section>

          <section
            class="ecm-module ecm-publisher-module"
            aria-labelledby="ecm-publisher-title"
          >
            <header>
              <h3 id="ecm-publisher-title">
                Top publishers
              </h3>
              <span>
                ${modelTopPublishers.length}
                represented
              </span>
            </header>

            <div
              class="ecm-module-body ecm-module-scroll"
              role="region"
              aria-label="Complete publisher ranking"
              tabindex="0"
            >
              ${renderPublisherRows()}
            </div>
          </section>

          <section
            class="ecm-module ecm-volume-module"
            aria-labelledby="ecm-volume-title"
          >
            <header>
              <h3 id="ecm-volume-title">
                Daily volume
              </h3>

              <span>
                7-day total
                <strong>${dailyTotal}</strong>
              </span>
            </header>

            <div class="ecm-module-body">
              ${renderDailyVolume()}
            </div>
          </section>
        </div>
      </div>
    `;
  };

  const renderToolbar = () => {
    const publishers =
      uniqueSorted(
        records.map(
          record => record.publisher
        )
      );

    const candidates =
      uniqueSorted(
        records.flatMap(
          record => record.candidates
        )
      );

    const hasCandidateFilter =
      candidates.length > 0;

    return `
      <form
        class="ecm-toolbar ${
          hasCandidateFilter
            ? "has-candidate-filter"
            : "without-candidate-filter"
        }"
        data-ecm-toolbar
        role="search"
      >
        <div class="ecm-search-control">
          <label
            class="ecm-visually-hidden"
            for="ecm-search"
          >
            Search coverage
          </label>

          <span aria-hidden="true">⌕</span>

          <input
            id="ecm-search"
            type="search"
            placeholder="Search coverage"
            autocomplete="off"
            data-ecm-search
            aria-controls="ecm-feed-list"
          >
        </div>

        <div class="ecm-select-control">
          <label
            class="ecm-visually-hidden"
            for="ecm-publisher"
          >
            Filter by publisher
          </label>

          <select
            id="ecm-publisher"
            data-ecm-publisher
            aria-controls="ecm-feed-list"
          >
            <option value="">
              All publishers
            </option>

            ${optionMarkup(publishers)}
          </select>
        </div>

        ${
          hasCandidateFilter
            ? `
              <div class="ecm-select-control">
                <label
                  class="ecm-visually-hidden"
                  for="ecm-candidate"
                >
                  Filter by candidate
                </label>

                <select
                  id="ecm-candidate"
                  data-ecm-candidate
                  aria-controls="ecm-feed-list"
                >
                  <option value="">
                    All candidates
                  </option>

                  ${optionMarkup(candidates)}
                </select>
              </div>
            `
            : ""
        }

        <div class="ecm-select-control">
          <label
            class="ecm-visually-hidden"
            for="ecm-sort"
          >
            Sort coverage
          </label>

          <select
            id="ecm-sort"
            data-ecm-sort
            aria-controls="ecm-feed-list"
          >
            <option value="newest">
              Newest first
            </option>

            <option value="oldest">
              Oldest first
            </option>
          </select>
        </div>
      </form>
    `;
  };
  const renderBody = () => `
    <div class="ecm-shell">
      <nav
        class="ecm-tabs"
        role="tablist"
        aria-label="Election coverage views"
      >
        <button
          id="ecm-coverage-tab"
          type="button"
          role="tab"
          aria-selected="true"
          aria-controls="ecm-coverage-panel"
          tabindex="0"
          data-ecm-tab="coverage"
        >
          Coverage
        </button>

        <button
          id="ecm-intelligence-tab"
          type="button"
          role="tab"
          aria-selected="false"
          aria-controls="ecm-intelligence-panel"
          tabindex="-1"
          data-ecm-tab="intelligence"
        >
          Coverage Intelligence
        </button>
      </nav>

      <div class="ecm-tab-panels">
        <section
          class="ecm-tab-panel ecm-coverage-panel"
          id="ecm-coverage-panel"
          role="tabpanel"
          aria-labelledby="ecm-coverage-tab"
          data-ecm-panel="coverage"
        >
          ${renderToolbar()}

          <div class="ecm-coverage-summary">
            <span>
              ${records.length} recent records
            </span>

            <span>
              ${publisherCounts().length} publishers
            </span>

            <span>
              ${latest24HourCount()} in latest 24h
            </span>

            <span>
              ${escapeHtml(
                coverageWindowLabel()
              )}
            </span>
          </div>

          <section
            class="ecm-feed"
            aria-labelledby="ecm-feed-title"
          >
            <header class="ecm-feed-header">
              <h3 id="ecm-feed-title">
                Recent election coverage
              </h3>

              <span
                data-ecm-result-summary
                aria-live="polite"
                aria-atomic="true"
              ></span>
            </header>

            <div
              class="ecm-feed-list"
              id="ecm-feed-list"
              data-ecm-feed-list
              role="feed"
              aria-label="Recent accepted election coverage"
              tabindex="0"
            ></div>
          </section>
        </section>

        <section
          class="ecm-tab-panel"
          id="ecm-intelligence-panel"
          role="tabpanel"
          aria-labelledby="ecm-intelligence-tab"
          data-ecm-panel="intelligence"
          hidden
        >
          ${renderIntelligence()}
        </section>
      </div>

      <footer class="ecm-disclosure">
        <span aria-hidden="true">ⓘ</span>

        <span>
          Source-linked automated collection
          · No editorial verification
        </span>

        <span>
          Coverage is not a representative
          measure of all French media
        </span>
      </footer>
    </div>
  `;

  const setActiveTab = (
    requestedTab,
    moveFocus = false
  ) => {
    const activeTab =
      requestedTab === "intelligence"
        ? "intelligence"
        : "coverage";

    state.activeTab = activeTab;

    const buttons = [
      ...modal.querySelectorAll(
        "[data-ecm-tab]"
      )
    ];

    const panels = [
      ...modal.querySelectorAll(
        "[data-ecm-panel]"
      )
    ];

    buttons.forEach(button => {
      const selected =
        button.dataset.ecmTab ===
        activeTab;

      button.setAttribute(
        "aria-selected",
        String(selected)
      );

      button.tabIndex =
        selected
          ? 0
          : -1;
    });

    panels.forEach(panel => {
      panel.hidden =
        panel.dataset.ecmPanel !==
        activeTab;
    });

    if (moveFocus) {
      buttons
        .find(
          button =>
            button.dataset.ecmTab ===
            activeTab
        )
        ?.focus();
    }
  };

  const resetState = () => {
    state.query = "";
    state.publisher = "";
    state.candidate = "";
    state.sort = "newest";
    state.activeTab = "coverage";
  };

  const bindControls = () => {
    const form = modal.querySelector(
      "[data-ecm-toolbar]"
    );

    const search = modal.querySelector(
      "[data-ecm-search]"
    );

    const publisher = modal.querySelector(
      "[data-ecm-publisher]"
    );

    const candidate = modal.querySelector(
      "[data-ecm-candidate]"
    );

    const sort = modal.querySelector(
      "[data-ecm-sort]"
    );

    form?.addEventListener(
      "submit",
      event => {
        event.preventDefault();
      }
    );

    search?.addEventListener(
      "input",
      event => {
        state.query =
          event.currentTarget.value;

        updateFeed();
      }
    );

    publisher?.addEventListener(
      "change",
      event => {
        state.publisher =
          event.currentTarget.value;

        updateFeed();
      }
    );

    candidate?.addEventListener(
      "change",
      event => {
        state.candidate =
          event.currentTarget.value;

        updateFeed();
      }
    );

    sort?.addEventListener(
      "change",
      event => {
        state.sort =
          event.currentTarget.value;

        updateFeed();
      }
    );

    const tabs = [
      ...modal.querySelectorAll(
        "[data-ecm-tab]"
      )
    ];

    tabs.forEach(
      (tab, index) => {
        tab.addEventListener(
          "click",
          () => {
            setActiveTab(
              tab.dataset.ecmTab,
              false
            );
          }
        );

        tab.addEventListener(
          "keydown",
          event => {
            const keys = [
              "ArrowLeft",
              "ArrowRight",
              "Home",
              "End"
            ];

            if (!keys.includes(event.key)) {
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

            setActiveTab(
              tabs[nextIndex]
                .dataset.ecmTab,
              true
            );
          }
        );
      }
    );
  };

  const focusableElements = () =>
    [
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
        element.getAttribute("aria-hidden") !==
          "true"
    );

  const close = () => {
    if (!modal || modal.hidden) return;

    modal.hidden = true;

    document.body.classList.remove(
      "ecm-is-open"
    );

    modal
      .querySelector(".ecm-body")
      .replaceChildren();

    const target = returnFocus;

    if (
      target &&
      document.contains(target)
    ) {
      target.setAttribute(
        "aria-expanded",
        "false"
      );
    }

    returnFocus = null;
    records = [];
    contextTopics = [];
    topicContextDays = 0;
    modelTopPublishers = [];
    candidateCoverageLeaders = [];
    comparisonQuality = {};
    latestPeriodLabel = "";
    priorPeriodLabel = "";
    dailyActivity = [];
    activityMax = 1;
    resetState();

    if (
      target &&
      document.contains(target)
    ) {
      target.focus();
    }
  };

  const ensureModal = () => {
    if (modal) return modal;

    document.body.insertAdjacentHTML(
      "beforeend",
      `
        <div
          class="ecm-overlay"
          id="election-coverage-modal"
          hidden
        >
          <section
            class="ecm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="ecm-title"
            aria-describedby="ecm-subtitle"
          >
            <header class="ecm-header">
              <div class="ecm-heading">
                <h2 id="ecm-title">
                  Media Pulse / Election Coverage
                </h2>

                <p id="ecm-subtitle">
                  Recent accepted reporting from
                  monitored sources
                </p>
              </div>

              <div class="ecm-header-actions">
                <span
                  class="ecm-updated"
                  data-ecm-updated
                ></span>

                <button
                  class="ecm-close"
                  type="button"
                  aria-label="Close election coverage"
                  data-ecm-close
                >
                  ×
                </button>
              </div>
            </header>

            <div class="ecm-body"></div>
          </section>
        </div>
      `
    );

    modal = document.getElementById(
      "election-coverage-modal"
    );

    modal.addEventListener(
      "click",
      event => {
        if (
          event.target === modal ||
          event.target.closest(
            "[data-ecm-close]"
          )
        ) {
          close();
        }
      }
    );

    document.addEventListener(
      "keydown",
      event => {
        if (!modal || modal.hidden) return;

        if (event.key === "Escape") {
          event.preventDefault();
          close();
          return;
        }

        if (event.key !== "Tab") return;

        const focusable =
          focusableElements();

        if (!focusable.length) return;

        const first = focusable[0];
        const last =
          focusable[
            focusable.length - 1
          ];

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
      }
    );

    return modal;
  };

  const open = (
    model,
    trigger = null
  ) => {
    if (
      !model ||
      model.state !== "ready" ||
      !Array.isArray(model.feedItems)
    ) {
      return;
    }

    ensureModal();
    resetState();

    records =
      normalizeRecords(model);

    contextTopics =
      Array.isArray(model.topicCoverage)
        ? model.topicCoverage
            .map(item => {
              const rawMetric =
                item?.sourceDays ??
                item?.itemCount ??
                0;

              const parsedMetric =
                Number(rawMetric);

              return {
                label:
                  String(
                    item?.label || ""
                  ).trim(),
                metric:
                  Number.isFinite(
                    parsedMetric
                  )
                    ? parsedMetric
                    : 0
              };
            })
            .filter(
              item =>
                item.label &&
                item.metric > 0
            )
        : [];

    const parsedContextDays =
      Number(model.windowDays);

    topicContextDays =
      Number.isFinite(parsedContextDays)
        ? parsedContextDays
        : 0;

    const publisherSource =
      Array.isArray(model.publisherRanking)
        ? model.publisherRanking
        : (
            Array.isArray(model.topPublishers)
              ? model.topPublishers
              : []
          );

    modelTopPublishers =
      publisherSource
        .map(item => ({
          name:
            String(
              item?.name || ""
            ).trim(),
          count:
            numberValue(
              item?.count
            )
        }))
        .filter(
          item =>
            item.name &&
            item.count > 0
        );

    const candidateSource =
      Array.isArray(model.candidateCoverage)
        ? model.candidateCoverage
        : (
            Array.isArray(
              model.candidateCoverageLeaders
            )
              ? model.candidateCoverageLeaders
              : []
          );

    candidateCoverageLeaders =
      [...candidateSource];

    comparisonQuality =
      model.comparisonQuality &&
      typeof model.comparisonQuality ===
        "object"
        ? model.comparisonQuality
        : {};

    latestPeriodLabel =
      String(
        model.latestPeriodLabel || ""
      ).trim();

    priorPeriodLabel =
      String(
        model.priorPeriodLabel || ""
      ).trim();

    dailyActivity =
      Array.isArray(model.dailyActivity)
        ? model.dailyActivity
            .slice(-7)
        : [];

    activityMax = Math.max(
      1,
      numberValue(model.activityMax),
      ...dailyActivity.map(
        day => numberValue(day.count)
      )
    );

    returnFocus =
      trigger instanceof HTMLElement
        ? trigger
        : null;

    if (returnFocus) {
      returnFocus.setAttribute(
        "aria-expanded",
        "true"
      );
    }

    const latest =
      latestRecord();

    const updated =
      model.generatedAt ||
      model.latestAcceptedAt ||
      latest?.publishedAt;

    modal.querySelector(
      "[data-ecm-updated]"
    ).textContent =
      `Updated: ${formatTimestamp(updated)}`;

    modal
      .querySelector(".ecm-body")
      .innerHTML = renderBody();

    bindControls();
    setActiveTab("coverage");
    updateFeed();

    modal.hidden = false;

    document.body.classList.add(
      "ecm-is-open"
    );

    requestAnimationFrame(() => {
      modal
        .querySelector("[data-ecm-search]")
        ?.focus();
    });
  };

  window.France2027ElectionCoverageModal = {
    open,
    close
  };
})();
