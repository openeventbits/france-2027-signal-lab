(() => {
  "use strict";

  const grid =
    document.querySelector("[data-candidate-directory-grid]");
  const disclosure =
    document.querySelector("[data-candidate-disclosure]");
  const toggle =
    document.querySelector("[data-candidate-potential-toggle]");
  const search =
    document.querySelector("[data-candidate-search]");
  const category =
    document.querySelector("[data-candidate-status]");
  const count =
    document.querySelector("[data-candidate-visible-count]");

  if (
    !grid ||
    !disclosure ||
    !toggle ||
    !search ||
    !category
  ) {
    return;
  }

  const cards = Array.from(
    grid.querySelectorAll("[data-candidate-card]")
  );

  /*
   * Initial directory depth by layout.
   *
   * Desktop: 20 cards = 5 complete four-column rows.
   * Tablet:  12 cards = 6 complete two-column rows.
   * Mobile:   8 cards.
   *
   * The generated HTML still contains all profiles.
   */
  const initialVisibleCount = () => {
    if (window.matchMedia("(min-width: 1350px)").matches) {
      return 20;
    }

    if (window.matchMedia("(min-width: 760px)").matches) {
      return 12;
    }

    return 8;
  };

  let expanded = false;

  const filterActive = () =>
    Boolean(
      search.value.trim() ||
      category.value
    );

  const updateCount = () => {
    if (!count) return;

    count.textContent = String(
      cards.filter(card => !card.hidden).length
    );
  };

  const sync = () => {
    /*
     * Search/category filtering is owned by candidate-hub.js.
     * When filtering, never conceal matching cards behind Show More.
     */
    if (filterActive()) {
      disclosure.hidden = true;
      updateCount();
      return;
    }

    const limit = initialVisibleCount();

    cards.forEach((card, index) => {
      card.hidden = !expanded && index >= limit;
    });

    const hasMore = cards.length > limit;

    disclosure.hidden = !hasMore;

    toggle.setAttribute(
      "aria-expanded",
      String(expanded)
    );

    const label = expanded
      ? toggle.dataset.expandedLabel
      : toggle.dataset.collapsedLabel;

    if (label) {
      toggle.textContent = label;
    }

    updateCount();
  };

  toggle.addEventListener("click", () => {
    expanded = !expanded;
    sync();
  });

  /*
   * candidate-hub.js is loaded first. Its search/category listener
   * therefore establishes card matches before this synchronizer runs.
   */
  search.addEventListener("input", sync);
  category.addEventListener("change", sync);

  window.addEventListener(
    "resize",
    () => {
      if (!expanded && !filterActive()) {
        sync();
      }
    },
    { passive: true }
  );

  /*
   * Progressive enhancement:
   * without JS, all generated profiles remain visible and crawlable.
   */
  disclosure.hidden = false;
  sync();
})();
