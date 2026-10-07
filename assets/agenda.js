(function () {
  "use strict";

  // Historical notes must dismiss without passing Escape to the shared dock.
  document.querySelectorAll(
    ".agenda-history-detail-page .agenda-note-tooltip"
  ).forEach(function (note) {
    function reopen() {
      note.classList.remove("is-dismissed");
    }
    note.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !note.classList.contains("is-dismissed")) {
        event.preventDefault();
        event.stopPropagation();
        note.classList.add("is-dismissed");
      }
    });
    note.addEventListener("focusin", reopen);
    note.addEventListener("mouseenter", reopen);
    note.addEventListener("click", reopen);
  });

  var search = document.querySelector("[data-agenda-search]");
  var grid = document.querySelector("[data-agenda-card-grid]");

  function normalize(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase();
  }

  if (grid) {
    var cards = Array.prototype.slice.call(
      grid.querySelectorAll("[data-agenda-card]")
    );
    var sortButtons = Array.prototype.slice.call(
      document.querySelectorAll("[data-agenda-sort]")
    );
    var currentEmpty = document.querySelector("[data-agenda-empty]");

    function numberAttribute(card, name) {
      var value = Number(card.getAttribute(name));
      return Number.isFinite(value) ? value : 0;
    }

    function compareCards(mode, a, b) {
      if (mode === "az") {
        return normalize(a.getAttribute("data-sort-label"))
          .localeCompare(normalize(b.getAttribute("data-sort-label")));
      }

      var attribute = mode === "movement"
        ? "data-sort-movement"
        : mode === "volume"
          ? "data-sort-volume"
          : "data-sort-activity";

      var primary =
        numberAttribute(b, attribute) -
        numberAttribute(a, attribute);

      if (primary !== 0) {
        return primary;
      }

      if (mode !== "activity") {
        var activity =
          numberAttribute(b, "data-sort-activity") -
          numberAttribute(a, "data-sort-activity");
        if (activity !== 0) {
          return activity;
        }
      }

      return normalize(a.getAttribute("data-sort-label"))
        .localeCompare(normalize(b.getAttribute("data-sort-label")));
    }

    function applyCurrentSearch() {
      var query = normalize(search ? search.value : "");
      var visible = 0;

      cards.forEach(function (card) {
        var name = normalize(card.getAttribute("data-name"));
        var matches = name.indexOf(query) !== -1;
        card.hidden = !matches;
        if (matches) {
          visible += 1;
        }
      });

      if (currentEmpty) {
        currentEmpty.hidden = visible !== 0;
      }
    }

    function setSort(mode) {
      cards
        .slice()
        .sort(function (a, b) {
          return compareCards(mode, a, b);
        })
        .forEach(function (card) {
          grid.appendChild(card);
        });

      sortButtons.forEach(function (button) {
        button.setAttribute(
          "aria-pressed",
          button.getAttribute("data-agenda-sort") === mode ? "true" : "false"
        );
      });
    }

    if (search) {
      search.addEventListener("input", applyCurrentSearch);
    }

    sortButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        setSort(button.getAttribute("data-agenda-sort") || "activity");
      });
    });

    // Fetch only on current hubs. Validate the complete payload before touching HTML.
    var liveUrl = grid.getAttribute("data-agenda-live-url");
    if (liveUrl && typeof fetch === "function") {
      var language = document.documentElement.lang === "fr" ? "fr" : "en";
      var family = "agenda";
      var hook = "data-agenda-live";
      function decimal(value) {
        return value.toFixed(1).replace(".", language === "fr" ? "," : ".");
      }
      function share(value) { return decimal(value * 100) + "%"; }
      function movement(value) {
        return (value > 0 ? "+" : value < 0 ? "−" : "") + decimal(Math.abs(value)) + "pp";
      }
      function dateParts(value) { return value.split("-").map(Number); }
      function dateLabels() { return JSON.parse(grid.getAttribute(hook + "-dates")); }
      function day(value) {
        var parts = dateParts(value);
        return parts[2] + " " + dateLabels().full[parts[1]] + " " + parts[0];
      }
      function period(p, window) {
        var start = p[window + "_start"], end = p[window + "_end"];
        var a = dateParts(start), b = dateParts(end), labels = dateLabels();
        if (start === end) { return day(start); }
        if (a[0] === b[0] && a[1] === b[1]) { return a[2] + "–" + b[2] + " " + labels.full[a[1]] + " " + a[0]; }
        return a[2] + " " + labels.short[a[1]] + (a[0] === b[0] ? "" : " " + a[0]) + "–" +
          b[2] + " " + labels.short[b[1]] + " " + b[0];
      }
      function count(value) { return Number.isSafeInteger(value) && value >= 0; }
      function fraction(value) { return Number.isFinite(value) && value >= 0 && value <= 1; }
      function isoDay(value) {
        return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
          Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
      }
      function snapshot(value) {
        if (typeof value !== "string" ||
            !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value) ||
            !isoDay(value.slice(0, 10))) { return null; }
        var instant = Date.parse(value);
        if (!Number.isFinite(instant)) { return null; }
        // Preserve source precision beyond JavaScript Date's milliseconds.
        return {second: Math.floor(instant / 1000),
          fraction: (value.match(/\.(\d+)/) || ["", ""])[1].replace(/0+$/, "")};
      }
      function valid(data) {
        var ids = JSON.parse(grid.getAttribute(hook + "-ids"));
        var liveSnapshot = data && snapshot(data.source_snapshot);
        var staticSnapshot = snapshot(grid.getAttribute(hook + "-snapshot"));
        if (!data || data.schema_version !== "1.0" || data.family !== family ||
            data.source !== "news_wire.json:campaign_agenda" || data.source_snapshot !== data.generated_at ||
            !liveSnapshot || !staticSnapshot || liveSnapshot.second < staticSnapshot.second ||
            (liveSnapshot.second === staticSnapshot.second && liveSnapshot.fraction < staticSnapshot.fraction) ||
            !data.period || !data.counts || !data.denominator || !Array.isArray(data.topics) ||
            data.topics.length !== ids.length) { return false; }
        var p = data.period;
        if (!["period_start", "period_end", "previous_start", "previous_end", "latest_start", "latest_end"]
            .every(function (key) { return isoDay(p[key]); }) || p.period_days !== 30 ||
            p.comparison_days !== 7 || p.period_end_partial !== true ||
            p.period_end !== new Date(data.source_snapshot).toISOString().slice(0, 10) ||
            Date.parse(p.period_end) - Date.parse(p.period_start) !== 29 * 86400000 ||
            Date.parse(p.latest_end) !== Date.parse(p.period_end) - 86400000 ||
            Date.parse(p.latest_end) - Date.parse(p.latest_start) !== 6 * 86400000 ||
            Date.parse(p.previous_end) !== Date.parse(p.latest_start) - 86400000 ||
            Date.parse(p.previous_end) - Date.parse(p.previous_start) !== 6 * 86400000) { return false; }
        if (!["input_item_count", "classified_item_count", "unclassified_item_count", "publisher_count", "rolling_assignment_count"]
            .every(function (key) { return count(data.counts[key]); }) ||
            data.counts.input_item_count !== data.counts.classified_item_count + data.counts.unclassified_item_count ||
            !["current", "previous", "latest"].every(function (key) { return count(data.denominator[key]); }) ||
            data.denominator.id !== "all_canonical_agenda_topic_source_days" || data.denominator.unit !== "agenda_topic_source_day" ||
            data.denominator.multilabel !== false || data.denominator.single_label !== true) { return false; }
        var seen = new Set();
        if (!data.topics.every(function (topic) {
          if (!topic || ids.indexOf(topic.id) === -1 || seen.has(topic.id)) { return false; }
          seen.add(topic.id);
          if (!["item_count", "source_day_count", "publisher_count", "active_day_count"]
              .every(function (key) { return count(topic[key]); }) ||
              typeof topic.display_eligible !== "boolean" || !fraction(topic.previous_share) ||
              !fraction(topic.latest_share) || !Number.isFinite(topic.movement_pp) ||
              Math.abs(topic.movement_pp - (topic.latest_share - topic.previous_share) * 100) > 0.001 ||
              !Array.isArray(topic.daily_activity) || topic.daily_activity.length !== 30) { return false; }
          var items = 0, sources = 0, active = 0;
          var windows = {previous: 0, latest: 0};
          if (!topic.daily_activity.every(function (point, index) {
            if (!point || !isoDay(point.date) || Date.parse(point.date) !== Date.parse(p.period_start) + index * 86400000 ||
                !count(point.item_count) || !count(point.source_day_count) || point.source_day_count > point.item_count) { return false; }
            items += point.item_count; sources += point.source_day_count; active += point.source_day_count > 0 ? 1 : 0;
            ["previous", "latest"].forEach(function (window) {
              if (p[window + "_start"] <= point.date && point.date <= p[window + "_end"]) { windows[window] += point.source_day_count; }
            });
            return true;
          })) { return false; }
          return items === topic.item_count && sources === topic.source_day_count && active === topic.active_day_count &&
            ["previous", "latest"].every(function (window) {
              var denom = data.denominator[window];
              return Math.abs(topic[window + "_share"] - (denom ? windows[window] / denom : 0)) <= 0.000001;
            });
        })) { return false; }
        if (data.topics.reduce(function (sum, topic) { return sum + topic.item_count; }, 0) !== data.counts.rolling_assignment_count ||
            data.topics.reduce(function (sum, topic) { return sum + topic.source_day_count; }, 0) !== data.denominator.current ||
            !data.topics.every(function (topic) { return Array.isArray(topic.matched_term_counts) &&
              topic.matched_term_counts.every(function (term) { return term && typeof term.term === "string" && count(term.item_count); }); })) { return false; }
        var compositionData = data;
        var compositionIds = compositionData.topics.map(function (t) { return t.id; });
        if (new Set(compositionIds).size !== compositionIds.length ||
            !Array.prototype.every.call(document.querySelectorAll("[" + hook + "-composition], [" + hook + "-segment]"), function (element) {
              return compositionIds.indexOf(element.getAttribute(hook + "-composition") || element.getAttribute(hook + "-segment")) !== -1;
            }) || !Array.prototype.every.call(document.querySelectorAll("[" + hook + "-movement]"), function (element) {
              return seen.has(element.getAttribute(hook + "-movement"));
            })) { return false; }
        if (!["previous", "latest"].every(function (window) {
          var total = data.topics.reduce(function (sum, topic) {
            return sum + topic.daily_activity.reduce(function (n, point) {
              return n + (p[window + "_start"] <= point.date && point.date <= p[window + "_end"] ? point.source_day_count : 0);
            }, 0);
          }, 0);
          return total === data.denominator[window];
        })) { return false; }
        return cards.every(function (card) {
          return seen.has(card.getAttribute("data-topic-id")) &&
            ["count", "publishers", "share", "movement", "signal"].every(function (key) {
              return !!card.querySelector("[" + hook + "='" + key + "']");
            }) && !!card.querySelector("[" + hook + "-bars]") && !!card.querySelector("[" + hook + "-state]");
        });
      }
      function setText(root, selector, value) {
        var element = root.querySelector(selector);
        if (element) { element.textContent = value; }
      }
      function enhance(data) {
        if (!valid(data)) { return; }
        var topics = new Map(data.topics.map(function (topic) { return [topic.id, topic]; }));
        var p = data.period;
        cards.forEach(function (card) {
          var topic = topics.get(card.getAttribute("data-topic-id"));
          card.setAttribute("data-sort-activity", topic.latest_share);
          card.setAttribute("data-sort-movement", Math.abs(topic.movement_pp));
          card.setAttribute("data-sort-volume", topic.item_count);
          setText(card, "[" + hook + "='count']", topic.source_day_count);
          setText(card, "[" + hook + "='publishers']", topic.publisher_count);
          setText(card, "[" + hook + "='share']", share(topic.latest_share));
          setText(card, "[" + hook + "='movement']", movement(topic.movement_pp));
          var signal = topic.matched_term_counts.length ? topic.matched_term_counts[0].term : "—";
          setText(card, "[" + hook + "='signal']", signal);
          var state = card.querySelector("[" + hook + "-state]");
          var lifecycle = topic.display_eligible ? "current" :
            (state.getAttribute("data-historical-qualified") === "true" ? "historical" : "dormant");
          state.className = "agenda-state is-" + lifecycle;
          state.textContent = (language === "fr" ? {current: "ACTUEL", historical: "HISTORIQUE", dormant: "DORMANT"} :
            {current: "CURRENT", historical: "HISTORICAL", dormant: "DORMANT"})[lifecycle];
          var bars = card.querySelector("[" + hook + "-bars]");
          var maximum = Math.max.apply(null, topic.daily_activity.map(function (point) { return point.source_day_count; })) || 1;
          var fragment = document.createDocumentFragment();
          topic.daily_activity.forEach(function (point) {
            var bar = document.createElement("i");
            var value = point.source_day_count;
            bar.className = p.previous_start <= point.date && point.date <= p.previous_end ? "is-previous" :
              p.latest_start <= point.date && point.date <= p.latest_end ? "is-recent" :
                point.date > p.latest_end ? "is-partial" : "is-older";
            bar.style.setProperty("--agenda-bar", (value === 0 ? 6 : Math.max(12, value / maximum * 100)).toFixed(1) + "%");
            bar.setAttribute("data-date", point.date);
            bar.setAttribute("data-source-days", value);
            bar.title = day(point.date) + " · " + value + " " + (language === "fr" ? "jours-sources" : "source-days");
            fragment.appendChild(bar);
          });
          bars.replaceChildren(fragment);
          bars.setAttribute("aria-label", (language === "fr" ? "Jours-sources par jour sur 30 jours : " : "Daily source-days over 30 days: ") +
            topic.daily_activity.map(function (point) { return point.source_day_count; }).join(", "));
        });
        var metrics = {items: data.counts.rolling_assignment_count, "source-days": data.denominator.current,
          publishers: data.counts.publisher_count, period: period(p, "period")};
        Object.keys(metrics).forEach(function (key) {
          setText(document, "[" + hook + "-metric='" + key + "']", metrics[key]);
        });
        var maximum = Math.max.apply(null, data.topics.map(function (topic) {
          return Math.max(topic.previous_share, topic.latest_share) * 100;
        })) || 1;
        var movementRows = Array.prototype.slice.call(document.querySelectorAll("[" + hook + "-movement]"));
        movementRows.forEach(function (row) {
          var t = topics.get(row.getAttribute(hook + "-movement"));
          var previous = t.previous_share * 100 / maximum * 100;
          var latest = t.latest_share * 100 / maximum * 100;
          var connector = row.querySelector(".agenda-dumbbell-connector");
          connector.style.setProperty("--agenda-low", Math.min(previous, latest) + "%");
          connector.style.setProperty("--agenda-span", Math.abs(previous - latest) + "%");
          row.querySelector(".agenda-dumbbell-dot.is-previous").style.setProperty("--agenda-position", previous + "%");
          row.querySelector(".agenda-dumbbell-dot.is-recent").style.setProperty("--agenda-position", latest + "%");
          var values = row.querySelectorAll(".agenda-dumbbell-values span");
          values[0].textContent = share(t.previous_share); values[1].textContent = share(t.latest_share);
          setText(row, ".agenda-dumbbell-delta", movement(t.movement_pp));
        });
        movementRows.sort(function (a, b) {
          var x = topics.get(a.getAttribute(hook + "-movement")), y = topics.get(b.getAttribute(hook + "-movement"));
          return Math.abs(y.movement_pp) - Math.abs(x.movement_pp) || y.latest_share - x.latest_share || x.id.localeCompare(y.id);
        }).forEach(function (row) { row.parentNode.appendChild(row); });
        var composition = {topics: data.topics, previous_total: data.denominator.previous, latest_total: data.denominator.latest};
        var compositionTopics = new Map(composition.topics.map(function (topic) { return [topic.id, topic]; }));
        document.querySelectorAll("[" + hook + "-composition]").forEach(function (row) {
          var t = compositionTopics.get(row.getAttribute(hook + "-composition"));
          var values = row.querySelectorAll("strong");
          values[0].textContent = share(t.previous_share); values[1].textContent = share(t.latest_share);
        });
        document.querySelectorAll("[" + hook + "-segment]").forEach(function (segment) {
          var t = compositionTopics.get(segment.getAttribute(hook + "-segment"));
          var window = segment.getAttribute("data-live-window");
          var value = t[window + "_share"] * 100;
          segment.style.setProperty("--agenda-share", value + "%");
          var label = cards.find(function (card) { return card.getAttribute("data-topic-id") === t.id; }).getAttribute("data-name");
          segment.title = label + " · " + decimal(value) + "%";
          if (family === "issues") {
            segment.replaceChildren();
            if (value >= 7) { var number = document.createElement("b"); number.textContent = t.position + 1; segment.appendChild(number); }
          }
        });
        ["previous", "latest"].forEach(function (window) {
          setText(document, "[" + hook + "-period='comparison-" + window + "']", period(p, window));
          setText(document, "[" + hook + "-period='composition-" + window + "']",
            period(p, window) + " · n=" + composition[window + "_total"]);
        });
        var activeSort = sortButtons.find(function (button) { return button.getAttribute("aria-pressed") === "true"; });
        setSort(activeSort ? activeSort.getAttribute("data-agenda-sort") : "activity");
        applyCurrentSearch();
      }
      fetch(liveUrl, {cache: "no-store", credentials: "same-origin"})
        .then(function (response) { if (!response.ok) { throw new Error("Live data unavailable"); } return response.json(); })
        .then(enhance)
        .catch(function () { /* Keep the complete static snapshot on failure. */ });
    }

  }

  Array.prototype.slice.call(
    document.querySelectorAll("[data-history-panel]")
  ).forEach(function (panel) {
    var modeButtons = Array.prototype.slice.call(
      panel.querySelectorAll("[data-history-mode]")
    );
    var series = Array.prototype.slice.call(
      panel.querySelectorAll("[data-history-series]")
    );
    var scale = panel.querySelector("[data-history-scale]");
    var unit = panel.querySelector("[data-history-unit]");
    var language = document.documentElement.lang === "fr" ? "fr" : "en";

    function setHistoryMode(mode) {
      modeButtons.forEach(function (button) {
        button.setAttribute(
          "aria-pressed",
          button.getAttribute("data-history-mode") === mode ? "true" : "false"
        );
      });
      series.forEach(function (line) {
        line.hidden = line.getAttribute("data-history-series") !== mode;
      });
      if (unit) {
        unit.textContent = mode === "volume"
          ? (language === "fr" ? "JOURS-SOURCES PAR JOUR" : "SOURCE-DAYS PER DAY")
          : (language === "fr" ? "POURCENTAGE DE L’AGENDA" : "AGENDA PERCENTAGE");
      }
      if (scale) {
        var maximum = panel.getAttribute(
          mode === "volume" ? "data-volume-maximum" : "data-share-maximum"
        );
        if (maximum) {
          scale.textContent = mode === "volume"
            ? "0–" + maximum + (language === "fr" ? " jours-sources" : " source-days")
            : "0–" + maximum + "%";
        }
      }
    }

    modeButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        setHistoryMode(button.getAttribute("data-history-mode") || "volume");
      });
    });
  });
})();
