(function () {
  "use strict";

  var search = document.querySelector("[data-issue-search]");
  var grid = document.querySelector("[data-issue-card-grid]");

  function normalize(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase();
  }

  if (grid) {
    var cards = Array.prototype.slice.call(
      grid.querySelectorAll("[data-issue-card]")
    );
    var sortButtons = Array.prototype.slice.call(
      document.querySelectorAll("[data-issue-sort]")
    );
    var currentEmpty = document.querySelector("[data-issue-empty]");

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
          button.getAttribute("data-issue-sort") === mode ? "true" : "false"
        );
      });
    }

    if (search) {
      search.addEventListener("input", applyCurrentSearch);
    }

    sortButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        setSort(button.getAttribute("data-issue-sort") || "activity");
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
          ? (language === "fr" ? "ARTICLES PAR JOUR" : "ITEMS PER DAY")
          : (language === "fr" ? "POURCENTAGE DU CORPUS" : "PERCENT OF CORPUS");
      }
      if (scale) {
        var maximum = panel.getAttribute(
          mode === "volume" ? "data-volume-maximum" : "data-share-maximum"
        );
        if (maximum) {
          scale.textContent = mode === "volume"
            ? "0–" + maximum + (language === "fr" ? " articles" : " items")
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
