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
