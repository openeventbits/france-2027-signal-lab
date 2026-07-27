(() => {
  "use strict";

  let modal = null;
  let returnFocus = null;
  let candidates = [];
  let topics = [];
  let selectedView = "topics";
  let selectedCandidateName = "";
  let selectedTopicId = "";
  let latestPeriodLabel = "";
  let priorPeriodLabel = "";
  let generatedAt = "";

  const state = {
    query: "",
    sort: "source-days"
  };

  const collator = new Intl.Collator("en", {
    sensitivity: "base"
  });

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
      .replace(/[^a-z0-9]+/g, " ")
      .trim();

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

  const safeUrl = value => {
    try {
      const parsed = new URL(
        String(value || ""),
        window.location.href
      );

      return ["http:", "https:"].includes(parsed.protocol)
        ? parsed.href
        : "";
    } catch {
      return "";
    }
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

  const formatDay = value => {
    const parsed = parseTimestamp(value);
    if (!parsed) return "Date unavailable";

    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "Europe/Paris"
    }).format(parsed);
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

  const normalizeArticle = (item, period = "") => ({
    id: String(item?.id || item?.url || ""),
    publisher:
      String(item?.publisher || "Unknown publisher").trim() ||
      "Unknown publisher",
    publishedAt: String(item?.published_at || ""),
    timestamp:
      parseTimestamp(item?.published_at)?.getTime() || 0,
    headline:
      String(item?.headline || "Untitled coverage record").trim() ||
      "Untitled coverage record",
    url: String(item?.url || ""),
    period
  });

  const dedupeArticles = values => {
    const records = new Map();

    values.forEach(item => {
      const key =
        item.id ||
        safeUrl(item.url) ||
        `${item.publisher}|${item.publishedAt}|${item.headline}`;

      if (!records.has(key)) records.set(key, item);
    });

    return [...records.values()].sort(
      (a, b) =>
        b.timestamp - a.timestamp ||
        collator.compare(a.publisher, b.publisher)
    );
  };

  const normalizeCandidate = item => {
    const name =
      String(item?.name || "Unknown candidate").trim() ||
      "Unknown candidate";

    const latestItems = dedupeArticles(
      Array.isArray(item?.latestItems)
        ? item.latestItems.map(value =>
            normalizeArticle(value, "current")
          )
        : []
    );

    const previousItems = dedupeArticles(
      Array.isArray(item?.previousItems)
        ? item.previousItems.map(value =>
            normalizeArticle(value, "prior")
          )
        : []
    );

    return {
      name,
      latestCount: numberOrZero(
        item?.latestCount ?? latestItems.length
      ),
      previousCount: numberOrZero(
        item?.previousCount ?? previousItems.length
      ),
      latestShare: numberOrZero(item?.latestShare),
      previousShare: numberOrZero(item?.previousShare),
      changePp: numberOrZero(item?.changePp),
      latestItems,
      previousItems,
      searchText: normalizeSearch(
        [
          name,
          ...latestItems.map(value =>
            `${value.publisher} ${value.headline}`
          ),
          ...previousItems.map(value =>
            `${value.publisher} ${value.headline}`
          )
        ].join(" ")
      )
    };
  };

  const isGeneralTopic = topic => {
    const identity = normalizeSearch(
      topic?.id || topic?.label || ""
    );

    return (
      identity.startsWith("other ") ||
      identity.startsWith("other_") ||
      identity.includes("other campaign coverage")
    );
  };

  const normalizeTopic = topic => {
    const supportingItems = dedupeArticles(
      Array.isArray(topic?.supporting_items)
        ? topic.supporting_items.map(value =>
            normalizeArticle(value, "")
          )
        : []
    );

    const label =
      String(topic?.label || "Untitled topic").trim() ||
      "Untitled topic";

    return {
      id: String(topic?.id || label).trim() || label,
      label,
      sourceDays: numberOrZero(topic?.source_day_count),
      itemCount: numberOrZero(topic?.item_count),
      publisherCount: numberOrZero(topic?.publisher_count),
      activeDayCount: numberOrZero(topic?.active_day_count),
      supportingItems,
      searchText: normalizeSearch(
        [
          label,
          ...supportingItems.map(value =>
            `${value.publisher} ${value.headline}`
          )
        ].join(" ")
      )
    };
  };

  const resetState = () => {
    state.query = "";
    state.sort = selectedView === "candidates"
      ? "current-share"
      : "source-days";
  };

  const sortCandidates = values => {
    const sorted = [...values];

    sorted.sort((a, b) => {
      if (state.sort === "change") {
        return (
          b.changePp - a.changePp ||
          b.latestShare - a.latestShare ||
          collator.compare(a.name, b.name)
        );
      }

      if (state.sort === "articles") {
        return (
          b.latestCount - a.latestCount ||
          b.previousCount - a.previousCount ||
          collator.compare(a.name, b.name)
        );
      }

      if (state.sort === "name") {
        return collator.compare(a.name, b.name);
      }

      return (
        b.latestShare - a.latestShare ||
        b.changePp - a.changePp ||
        collator.compare(a.name, b.name)
      );
    });

    return sorted;
  };

  const sortTopics = values => {
    const sorted = [...values];

    sorted.sort((a, b) => {
      if (state.sort === "publishers") {
        return (
          b.publisherCount - a.publisherCount ||
          b.sourceDays - a.sourceDays ||
          collator.compare(a.label, b.label)
        );
      }

      if (state.sort === "items") {
        return (
          b.itemCount - a.itemCount ||
          b.sourceDays - a.sourceDays ||
          collator.compare(a.label, b.label)
        );
      }

      if (state.sort === "name") {
        return collator.compare(a.label, b.label);
      }

      return (
        b.sourceDays - a.sourceDays ||
        b.publisherCount - a.publisherCount ||
        collator.compare(a.label, b.label)
      );
    });

    return sorted;
  };

  const visibleCandidates = () => {
    const query = normalizeSearch(state.query);
    return sortCandidates(
      candidates.filter(candidate =>
        !query || candidate.searchText.includes(query)
      )
    );
  };

  const visibleTopics = () => {
    const query = normalizeSearch(state.query);
    return sortTopics(
      topics.filter(topic =>
        !query || topic.searchText.includes(query)
      )
    );
  };

  const selectedCandidate = values =>
    values.find(
      candidate => candidate.name === selectedCandidateName
    ) || values[0] || null;

  const selectedTopic = values =>
    values.find(
      topic => topic.id === selectedTopicId
    ) || values[0] || null;

  const renderMetric = (
    value,
    label,
    secondary = "",
    tone = ""
  ) => `
    <div class="tcm-metric${tone ? ` ${tone}` : ""}">
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(label)}</span>
      ${secondary
        ? `<small>${escapeHtml(secondary)}</small>`
        : ""}
    </div>
  `;

  const renderSourceLink = item => {
    const href = safeUrl(item.url);

    if (!href) {
      return `
        <span class="tcm-source-unavailable">
          Source unavailable
        </span>
      `;
    }

    return `
      <a
        class="tcm-source-link"
        href="${escapeAttribute(href)}"
        target="_blank"
        rel="noopener noreferrer"
      >
        Open source
        <span aria-hidden="true">↗</span>
      </a>
    `;
  };

  const renderCoverageRows = (values, showPeriod = false) => {
    if (!values.length) {
      return `
        <div class="tcm-detail-empty">
          No source-linked coverage is available for this selection.
        </div>
      `;
    }

    return values
      .map(item => `
        <article class="tcm-support-row">
          <div class="tcm-support-meta">
            <strong>${escapeHtml(item.publisher)}</strong>
            <time datetime="${escapeAttribute(item.publishedAt)}">
              ${escapeHtml(formatDay(item.publishedAt))}
            </time>
            ${showPeriod
              ? `<span class="tcm-period-chip is-${escapeAttribute(item.period)}">${escapeHtml(item.period)}</span>`
              : ""}
          </div>

          <h4 lang="fr">${escapeHtml(item.headline)}</h4>
          ${renderSourceLink(item)}
        </article>
      `)
      .join("");
  };

  const renderCandidateRow = (
    candidate,
    index,
    maximum
  ) => {
    const currentWidth = Math.min(
      100,
      candidate.latestShare / maximum * 100
    );
    const priorPosition = Math.min(
      100,
      candidate.previousShare / maximum * 100
    );
    const active = candidate.name === selectedCandidateName;
    const directionClass = deltaClass(candidate.changePp);

    return `
      <button
        class="tcm-candidate-row${active ? " is-selected" : ""}"
        type="button"
        data-tcm-candidate="${escapeAttribute(candidate.name)}"
        aria-pressed="${String(active)}"
        aria-label="${escapeAttribute(
          `${candidate.name}: ${formatShare(candidate.latestShare)} percent current, ${formatShare(candidate.previousShare)} percent prior, ${formatDelta(candidate.changePp)}.`
        )}"
      >
        <span class="tcm-row-rank">
          ${String(index + 1).padStart(2, "0")}
        </span>

        <span class="tcm-row-copy">
          <span class="tcm-row-head">
            <strong>${escapeHtml(candidate.name)}</strong>
            <b class="${directionClass}">
              ${deltaArrow(candidate.changePp)}
              ${escapeHtml(formatDelta(candidate.changePp))}
            </b>
          </span>

          <small>
            ${candidate.latestCount} current ·
            ${candidate.previousCount} prior
          </small>

          <i class="tcm-candidate-track" aria-hidden="true">
            <b style="--tcm-current-width:${currentWidth.toFixed(2)}%"></b>
            <em style="--tcm-prior-position:${priorPosition.toFixed(2)}%"></em>
          </i>
        </span>

        <span class="tcm-row-value">
          ${escapeHtml(formatShare(candidate.latestShare))}%
        </span>
      </button>
    `;
  };

  const renderCandidateRanking = values => {
    if (!values.length) {
      return `
        <div class="tcm-empty" role="status">
          <strong>No matching candidates</strong>
          <span>Adjust the search to show candidate coverage.</span>
        </div>
      `;
    }

    const maximum = Math.max(
      1,
      ...values.flatMap(candidate => [
        candidate.latestShare,
        candidate.previousShare
      ])
    );

    return values
      .map((candidate, index) =>
        renderCandidateRow(candidate, index, maximum)
      )
      .join("");
  };

  const renderTopicRow = (
    topic,
    index,
    maximum
  ) => {
    const width = Math.min(
      100,
      topic.sourceDays / maximum * 100
    );
    const active = topic.id === selectedTopicId;

    return `
      <button
        class="tcm-topic-row${active ? " is-selected" : ""}"
        type="button"
        data-tcm-topic="${escapeAttribute(topic.id)}"
        aria-pressed="${String(active)}"
      >
        <span class="tcm-row-rank">
          ${String(index + 1).padStart(2, "0")}
        </span>

        <span class="tcm-row-copy">
          <span class="tcm-row-head">
            <strong>${escapeHtml(topic.label)}</strong>
            <b>${topic.sourceDays} source-days</b>
          </span>

          <small>
            ${topic.itemCount} items ·
            ${topic.publisherCount} publishers ·
            ${topic.activeDayCount} active days
          </small>

          <i class="tcm-topic-track" aria-hidden="true">
            <b style="--tcm-topic-width:${width.toFixed(2)}%"></b>
          </i>
        </span>
      </button>
    `;
  };

  const renderTopicRanking = values => {
    if (!values.length) {
      return `
        <div class="tcm-empty" role="status">
          <strong>No matching topics</strong>
          <span>Adjust the search to show recurring topics.</span>
        </div>
      `;
    }

    const maximum = Math.max(
      1,
      ...values.map(topic => topic.sourceDays)
    );

    return values
      .map((topic, index) =>
        renderTopicRow(topic, index, maximum)
      )
      .join("");
  };

  const renderCandidateDetail = candidate => {
    if (!candidate) {
      return `
        <div class="tcm-detail-empty">
          Select a candidate to inspect the coverage behind the shift.
        </div>
      `;
    }

    const coverage = dedupeArticles([
      ...candidate.latestItems,
      ...candidate.previousItems
    ]);
    const tone = deltaClass(candidate.changePp);

    return `
      <div class="tcm-detail-content">
        <div class="tcm-detail-kicker">Selected candidate</div>
        <h3>${escapeHtml(candidate.name)}</h3>

        <div class="tcm-metrics">
          ${renderMetric(
            `${formatShare(candidate.latestShare)}%`,
            "Current share",
            latestPeriodLabel,
            "is-current"
          )}
          ${renderMetric(
            `${formatShare(candidate.previousShare)}%`,
            "Prior share",
            priorPeriodLabel,
            "is-prior"
          )}
          ${renderMetric(
            formatDelta(candidate.changePp),
            "Change",
            "percentage points",
            tone
          )}
          ${renderMetric(
            `${candidate.latestCount} / ${candidate.previousCount}`,
            "Articles",
            "current / prior"
          )}
        </div>

        <section class="tcm-supporting">
          <header class="tcm-supporting-head">
            <h4>Source-linked coverage</h4>
            <span>${coverage.length} records</span>
          </header>

          <div class="tcm-supporting-list">
            ${renderCoverageRows(coverage, true)}
          </div>
        </section>
      </div>
    `;
  };

  const renderTopicDetail = topic => {
    if (!topic) {
      return `
        <div class="tcm-detail-empty">
          Select a topic to inspect its supporting coverage.
        </div>
      `;
    }

    return `
      <div class="tcm-detail-content">
        <div class="tcm-detail-kicker">Selected topic</div>
        <h3>${escapeHtml(topic.label)}</h3>

        <div class="tcm-metrics">
          ${renderMetric(
            String(topic.sourceDays),
            "Source-days",
            "recurring coverage"
          )}
          ${renderMetric(
            String(topic.itemCount),
            "Accepted items"
          )}
          ${renderMetric(
            String(topic.publisherCount),
            "Publishers"
          )}
          ${renderMetric(
            String(topic.activeDayCount),
            "Active days"
          )}
        </div>

        <section class="tcm-supporting">
          <header class="tcm-supporting-head">
            <h4>Supporting coverage</h4>
            <span>${topic.supportingItems.length} source-linked items</span>
          </header>

          <div class="tcm-supporting-list">
            ${renderCoverageRows(topic.supportingItems)}
          </div>
        </section>
      </div>
    `;
  };

  const renderSortOptions = () => {
    const options = selectedView === "candidates"
      ? [
          ["current-share", "Sort: current share"],
          ["change", "Sort: change"],
          ["articles", "Sort: current articles"],
          ["name", "Sort: name"]
        ]
      : [
          ["source-days", "Sort: source-days"],
          ["publishers", "Sort: publishers"],
          ["items", "Sort: accepted items"],
          ["name", "Sort: name"]
        ];

    return options
      .map(([value, label]) => `
        <option
          value="${escapeAttribute(value)}"
          ${state.sort === value ? "selected" : ""}
        >${escapeHtml(label)}</option>
      `)
      .join("");
  };

  const renderBody = () => `
    <div class="tcm-shell">
      <div class="tcm-view-tabs" role="tablist" aria-label="Coverage analysis view">
        <button
          type="button"
          role="tab"
          data-tcm-view="candidates"
          aria-selected="${String(selectedView === "candidates")}"
        >Candidate shift</button>
        <button
          type="button"
          role="tab"
          data-tcm-view="topics"
          aria-selected="${String(selectedView === "topics")}"
        >Topic coverage</button>
      </div>

      <form class="tcm-toolbar" data-tcm-toolbar role="search">
        <div class="tcm-search-control">
          <label class="tcm-visually-hidden" for="tcm-search">
            Search ${selectedView === "candidates" ? "candidates" : "topics"}
          </label>
          <span aria-hidden="true">⌕</span>
          <input
            id="tcm-search"
            type="search"
            placeholder="Search ${selectedView === "candidates" ? "candidates or coverage" : "topics or coverage"}"
            autocomplete="off"
            data-tcm-search
            value="${escapeAttribute(state.query)}"
          >
        </div>

        <label class="tcm-sort-control">
          <span class="tcm-visually-hidden">Sort results</span>
          <select data-tcm-sort>
            ${renderSortOptions()}
          </select>
        </label>
      </form>

      <div class="tcm-workspace">
        <section class="tcm-ranking">
          <header class="tcm-ranking-head">
            <div>
              <h3 data-tcm-ranking-title></h3>
              <p data-tcm-ranking-subtitle></p>
            </div>
            <span data-tcm-result-summary aria-live="polite"></span>
          </header>

          <div class="tcm-ranking-list" data-tcm-ranking-list></div>
        </section>

        <section class="tcm-detail" data-tcm-detail aria-live="polite"></section>
      </div>
    </div>
  `;

  const renderShell = () => {
    modal.querySelector("[data-tcm-body]").innerHTML = renderBody();
    bindControls();
    updateView();
  };

  const updateView = () => {
    const list = modal?.querySelector("[data-tcm-ranking-list]");
    const detail = modal?.querySelector("[data-tcm-detail]");
    const summary = modal?.querySelector("[data-tcm-result-summary]");
    const title = modal?.querySelector("[data-tcm-ranking-title]");
    const subtitle = modal?.querySelector("[data-tcm-ranking-subtitle]");

    if (!list || !detail || !summary || !title || !subtitle) return;

    modal
      .querySelectorAll("[data-tcm-view]")
      .forEach(button => {
        button.setAttribute(
          "aria-selected",
          String(button.dataset.tcmView === selectedView)
        );
      });

    if (selectedView === "candidates") {
      const values = visibleCandidates();

      if (!values.some(value => value.name === selectedCandidateName)) {
        selectedCandidateName = values[0]?.name || "";
      }

      title.textContent = "Candidate visibility ranking";
      subtitle.textContent = "Current seven-day share compared with the prior seven days";
      summary.textContent = `${values.length} ${values.length === 1 ? "candidate" : "candidates"}`;
      list.innerHTML = renderCandidateRanking(values);
      detail.innerHTML = renderCandidateDetail(
        selectedCandidate(values)
      );
    } else {
      const values = visibleTopics();

      if (!values.some(value => value.id === selectedTopicId)) {
        selectedTopicId = values[0]?.id || "";
      }

      title.textContent = "Recurring topic ranking";
      subtitle.textContent = "Specific eligible topics ranked by source-day recurrence";
      summary.textContent = `${values.length} specific ${values.length === 1 ? "topic" : "topics"}`;
      list.innerHTML = renderTopicRanking(values);
      detail.innerHTML = renderTopicDetail(
        selectedTopic(values)
      );
    }
  };

  const bindControls = () => {
    const form = modal.querySelector("[data-tcm-toolbar]");
    const search = modal.querySelector("[data-tcm-search]");
    const sort = modal.querySelector("[data-tcm-sort]");
    const list = modal.querySelector("[data-tcm-ranking-list]");
    const tabs = modal.querySelector(".tcm-view-tabs");

    form?.addEventListener("submit", event => {
      event.preventDefault();
    });

    search?.addEventListener("input", event => {
      state.query = event.currentTarget.value;
      updateView();
    });

    sort?.addEventListener("change", event => {
      state.sort = event.currentTarget.value;
      updateView();
    });

    tabs?.addEventListener("click", event => {
      const button = event.target.closest("[data-tcm-view]");
      if (!button || button.dataset.tcmView === selectedView) return;

      selectedView = button.dataset.tcmView;
      state.query = "";
      state.sort = selectedView === "candidates"
        ? "current-share"
        : "source-days";
      renderShell();

      requestAnimationFrame(() => {
        modal.querySelector("[data-tcm-search]")?.focus();
      });
    });

    list?.addEventListener("click", event => {
      const candidateButton = event.target.closest("[data-tcm-candidate]");
      const topicButton = event.target.closest("[data-tcm-topic]");

      if (candidateButton) {
        selectedCandidateName = candidateButton.dataset.tcmCandidate;
        updateView();
        modal
          .querySelector(
            `[data-tcm-candidate="${CSS.escape(selectedCandidateName)}"]`
          )
          ?.focus();
        return;
      }

      if (topicButton) {
        selectedTopicId = topicButton.dataset.tcmTopic;
        updateView();
        modal
          .querySelector(
            `[data-tcm-topic="${CSS.escape(selectedTopicId)}"]`
          )
          ?.focus();
      }
    });
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
        element.getAttribute("aria-hidden") !== "true"
    );

  const reconcileReturnFocus = () => {
    if (!returnFocus || document.contains(returnFocus)) return;

    const targetAttribute = [
      "data-topic-coverage-open",
      "data-hybrid-media-topic",
      "data-hybrid-media-candidate"
    ].find(attribute => returnFocus.hasAttribute(attribute));

    if (!targetAttribute) return;

    const targetValue = returnFocus.getAttribute(targetAttribute);
    const replacement = [
      ...document.querySelectorAll(`[${targetAttribute}]`)
    ].find(
      element =>
        element.getAttribute(targetAttribute) === targetValue
    );

    if (!replacement) return;

    returnFocus = replacement;
    if (modal && !modal.hidden) {
      returnFocus.setAttribute("aria-expanded", "true");
    }
  };

  const close = () => {
    if (!modal || modal.hidden) return;

    modal.hidden = true;
    document.body.classList.remove("tcm-is-open");
    modal.querySelector("[data-tcm-body]").replaceChildren();

    reconcileReturnFocus();
    const target = returnFocus;
    if (target && document.contains(target)) {
      target.setAttribute("aria-expanded", "false");
    }

    returnFocus = null;
    candidates = [];
    topics = [];
    selectedCandidateName = "";
    selectedTopicId = "";
    latestPeriodLabel = "";
    priorPeriodLabel = "";
    generatedAt = "";
    state.query = "";

    if (target && document.contains(target)) target.focus();
  };

  const ensureModal = () => {
    if (modal) return modal;

    document.body.insertAdjacentHTML(
      "beforeend",
      `
        <div class="tcm-overlay" id="topic-coverage-modal" hidden>
          <section
            class="tcm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tcm-title"
          >
            <header class="tcm-header">
              <h2 id="tcm-title">Media Pulse / Coverage Analysis</h2>
              <div class="tcm-header-actions">
                <span class="tcm-updated" data-tcm-updated></span>
                <button
                  class="tcm-close"
                  type="button"
                  aria-label="Close coverage analysis"
                  data-tcm-close
                >×</button>
              </div>
            </header>

            <div class="tcm-body" data-tcm-body></div>
          </section>
        </div>
      `
    );

    modal = document.getElementById("topic-coverage-modal");

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

  const open = (
    models,
    trigger = null,
    options = {}
  ) => {
    const mediaModel = models?.media;
    const agendaModel = models?.agenda;

    candidates = Array.isArray(mediaModel?.candidateCoverage)
      ? mediaModel.candidateCoverage
          .map(normalizeCandidate)
          .filter(candidate => candidate.name)
      : [];

    topics = Array.isArray(agendaModel?.topics)
      ? agendaModel.topics
          .filter(topic => topic?.display_eligible)
          .filter(topic => !isGeneralTopic(topic))
          .map(normalizeTopic)
          .filter(topic => topic.supportingItems.length)
      : [];

    selectedView = options.initialView === "candidates"
      ? "candidates"
      : options.initialView === "topics"
        ? "topics"
        : topics.length
          ? "topics"
          : "candidates";

    selectedCandidateName = candidates.some(
      candidate => candidate.name === options.candidateName
    )
      ? options.candidateName
      : sortCandidates(candidates)[0]?.name || "";

    selectedTopicId = topics.some(
      topic => topic.id === options.topicId
    )
      ? options.topicId
      : sortTopics(topics)[0]?.id || "";

    latestPeriodLabel = String(
      mediaModel?.latestPeriodLabel || ""
    );
    priorPeriodLabel = String(
      mediaModel?.priorPeriodLabel || ""
    );
    generatedAt = String(
      mediaModel?.generatedAt ||
      agendaModel?.generatedAt ||
      ""
    );

    resetState();
    ensureModal();
    returnFocus = trigger;

    if (returnFocus && document.contains(returnFocus)) {
      returnFocus.setAttribute("aria-expanded", "true");
    }

    modal.querySelector("[data-tcm-updated]").textContent =
      `Updated: ${formatTimestamp(generatedAt)}`;

    renderShell();
    modal.hidden = false;
    document.body.classList.add("tcm-is-open");

    requestAnimationFrame(() => {
      modal.querySelector("[data-tcm-search]")?.focus();
    });
  };

  window.France2027TopicCoverageModal = {
    open,
    close,
    reconcileReturnFocus
  };
})();
