(() => {
  "use strict";

  let modal = null;
  let returnFocus = null;
  let records = [];
  let contextTopics = [];
  let topicContextDays = 0;
  const state = {
    query: "",
    publisher: "",
    candidate: "",
    sort: "newest"
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
    const publishers =
      publisherCounts().slice(0, 5);

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
        publisher => publisher.count
      )
    );

    return publishers
      .map(publisher => {
        const width =
          publisher.count /
          maximum *
          100;

        return `
          <div class="ecm-publisher-row">
            <span>
              ${escapeHtml(publisher.name)}
            </span>

            <i aria-hidden="true">
              <b
                style="--ecm-publisher-width:${width.toFixed(2)}%"
              ></b>
            </i>

            <strong>
              ${publisher.count}
            </strong>
          </div>
        `;
      })
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

  const renderContextTopics = () => {
    if (!contextTopics.length) {
      return `
        <p class="ecm-snapshot-empty">
          Topic context unavailable.
        </p>
      `;
    }

    return contextTopics
      .map(
        topic => `
          <div class="ecm-topic-row">
            <span>
              ${escapeHtml(topic.label)}
            </span>

            <strong>
              ${escapeHtml(topic.metric)}
            </strong>
          </div>
        `
      )
      .join("");
  };

  const renderSnapshot = () => {
    const publishers =
      publisherCounts();

    const contextLabel =
      topicContextDays > 0
        ? `${topicContextDays}-day context`
        : "Media Pulse context";

    return `
      <aside
        class="ecm-snapshot"
        aria-labelledby="ecm-snapshot-title"
      >
        <h3 id="ecm-snapshot-title">
          Coverage overview
        </h3>

        <dl class="ecm-snapshot-metrics">
          <div>
            <dt>Recent records</dt>
            <dd>${records.length}</dd>
          </div>

          <div>
            <dt>Publishers represented</dt>
            <dd>${publishers.length}</dd>
          </div>

          <div>
            <dt>Published in latest 24h</dt>
            <dd>${latest24HourCount()}</dd>
          </div>

          <div class="is-window">
            <dt>Coverage window</dt>
            <dd>
              ${escapeHtml(
                coverageWindowLabel()
              )}
            </dd>
          </div>
        </dl>

        <section
          class="ecm-publisher-section"
          aria-labelledby="ecm-publishers-title"
        >
          <h4 id="ecm-publishers-title">
            Top publishers
          </h4>

          <div class="ecm-publisher-list">
            ${renderPublisherRows()}
          </div>
        </section>

        <section
          class="ecm-topic-section"
          aria-labelledby="ecm-topics-title"
        >
          <h4 id="ecm-topics-title">
            Topics in focus
            <small>
              · source-days / ${escapeHtml(contextLabel)}
            </small>
          </h4>

          <div class="ecm-topic-list">
            ${renderContextTopics()}
          </div>
        </section>
      </aside>
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
      ${renderToolbar()}

      <div class="ecm-workspace">
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

        ${renderSnapshot()}
      </div>

      <footer class="ecm-disclosure">
        <span aria-hidden="true">ⓘ</span>
        <span>
          Source-linked automated collection
          · No editorial verification
        </span>
      </footer>
    </div>
  `;

  const resetState = () => {
    state.query = "";
    state.publisher = "";
    state.candidate = "";
    state.sort = "newest";
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
            .slice(0, 5)
        : [];

    const parsedContextDays =
      Number(model.windowDays);

    topicContextDays =
      Number.isFinite(parsedContextDays)
        ? parsedContextDays
        : 0;

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
