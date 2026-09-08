/* FR27 TIER 3
 * width < 1024px
 *
 * Slice 01:
 * - workspace selector
 * - candidate selector
 *
 * Layout remains CSS-owned.
 * No artificial Analysis/Dossier view state.
 */
(() => {
  "use strict";

  const tier3Query =
    window.matchMedia(
      "(width < 1024px)"
    );

  const root =
    document.documentElement;

  const hybridMount =
    document.getElementById(
      "hybrid-signal-board"
    );

  if (!hybridMount) return;


  const workspaceHashes =
    Object.freeze({
      candidates: "#signal-candidates",
      agenda: "#signal-agenda",
      events: "#signal-events",
      issues: "#signal-issues",
      runoff: "#signal-runoff"
    });


  const workspaceLabels =
    Object.freeze({
      candidates: "CANDIDATES",
      agenda: "AGENDA",
      events: "EVENTS",
      issues: "ISSUES",
      runoff: "RUNOFF"
    });


  let refreshQueued =
    false;


  function currentWorkspace() {

    const match =
      Object.entries(
        workspaceHashes
      ).find(
        ([, hash]) =>
          hash ===
          window.location.hash
      );

    return match
      ? match[0]
      : "candidates";
  }


  function createSelectControl(
    className,
    labelText,
    ariaLabel
  ) {

    const control =
      document.createElement(
        "div"
      );

    control.className =
      className;


    const label =
      document.createElement(
        "span"
      );

    label.className =
      "fr27-tier3-control-label";

    label.textContent =
      labelText;


    const wrap =
      document.createElement(
        "div"
      );

    wrap.className =
      "fr27-tier3-select-wrap";


    const select =
      document.createElement(
        "select"
      );

    select.className =
      "fr27-tier3-select";

    select.setAttribute(
      "aria-label",
      ariaLabel
    );


    wrap.append(
      select
    );

    control.append(
      label,
      wrap
    );


    return {
      control,
      select
    };
  }


  function ensureWorkspaceControl() {

    const workspace =
      hybridMount.querySelector(
        ".hybrid-workspace"
      );

    if (!workspace) return;


    let control =
      workspace.querySelector(
        "[data-tier3-workspace-control]"
      );

    let select;


    if (!control) {

      const created =
        createSelectControl(
          "fr27-tier3-workspace-control",
          "WORKSPACE",
          "Choose FR27 workspace"
        );


      control =
        created.control;

      select =
        created.select;

      control.dataset
        .tier3WorkspaceControl =
        "";


      Object.keys(
        workspaceHashes
      ).forEach(
        key => {

          const option =
            document.createElement(
              "option"
            );

          option.value =
            key;

          option.textContent =
            workspaceLabels[key];

          select.append(
            option
          );
        }
      );


      select.addEventListener(
        "change",
        () => {

          const key =
            select.value;

          const hash =
            workspaceHashes[key];

          if (!hash) return;


          if (
            window.location.hash ===
            hash
          ) {

            window
              .hybridDashboard
              ?.setActiveSignalView
              ?.(key);

          } else {

            window.location.hash =
              hash;
          }
        }
      );


      workspace.insertBefore(
        control,
        workspace.firstChild
      );

    } else {

      select =
        control.querySelector(
          "select"
        );
    }


    if (select) {

      select.value =
        currentWorkspace();
    }
  }


  function candidateButtons(
    candidateRoot
  ) {

    return [
      ...candidateRoot.querySelectorAll(
        ".candidate-signals-candidate-button"
      )
    ];
  }


  function candidateOptionLabel(
    button
  ) {

    const name =
      button.querySelector(
        ".candidate-signals-candidate-name"
      )?.textContent?.trim() ||
      "Candidate";


    const tier =
      String(
        button.dataset.candidateTier ||
        ""
      )
        .trim()
        .toUpperCase();


    const poll =
      button.querySelector(
        ".candidate-signals-candidate-poll"
      )?.textContent?.trim() ||
      "";


    return [
      name,
      tier,
      poll
    ]
      .filter(Boolean)
      .join(" · ");
  }


  function ensureCandidateControl() {

    const panel =
      document.getElementById(
        "signal-candidates-panel"
      );

    const candidateRoot =
      document.getElementById(
        "candidate-signals-root"
      );


    if (
      !panel ||
      !candidateRoot
    ) {
      return;
    }


    let control =
      panel.querySelector(
        "[data-tier3-candidate-control]"
      );

    let select;


    if (!control) {

      const created =
        createSelectControl(
          "fr27-tier3-candidate-control",
          "CANDIDATE MONITOR",
          "Choose candidate"
        );


      control =
        created.control;

      select =
        created.select;

      control.dataset
        .tier3CandidateControl =
        "";


      select.addEventListener(
        "change",
        () => {

          const currentRoot =
            document.getElementById(
              "candidate-signals-root"
            );

          if (!currentRoot) return;


          const target =
            candidateButtons(
              currentRoot
            ).find(
              button =>
                button.dataset
                  .candidateSignalsCandidate ===
                select.value
            );


          target?.click();

          queueRefresh();
        }
      );


      panel.insertBefore(
        control,
        candidateRoot
      );

    } else {

      select =
        control.querySelector(
          "select"
        );
    }


    if (!select) return;


    const buttons =
      candidateButtons(
        candidateRoot
      );


    if (!buttons.length) {

      if (
        select.dataset
          .optionSignature !==
        "loading"
      ) {

        const option =
          document.createElement(
            "option"
          );

        option.value =
          "";

        option.textContent =
          "Loading candidates…";


        select.replaceChildren(
          option
        );

        select.disabled =
          true;

        select.dataset
          .optionSignature =
          "loading";
      }

      return;
    }


    const signature =
      buttons
        .map(
          button =>
            [
              button.dataset
                .candidateSignalsCandidate,

              candidateOptionLabel(
                button
              )
            ].join(":")
        )
        .join("|");


    if (
      select.dataset
        .optionSignature !==
      signature
    ) {

      const options =
        buttons.map(
          button => {

            const option =
              document.createElement(
                "option"
              );

            option.value =
              button.dataset
                .candidateSignalsCandidate ||
              "";

            option.textContent =
              candidateOptionLabel(
                button
              );

            return option;
          }
        );


      select.replaceChildren(
        ...options
      );

      select.dataset
        .optionSignature =
        signature;

      select.disabled =
        false;
    }


    const selected =
      buttons.find(
        button =>
          button.getAttribute(
            "aria-pressed"
          ) === "true"
      );


    if (
      selected?.dataset
        .candidateSignalsCandidate
    ) {

      select.value =
        selected.dataset
          .candidateSignalsCandidate;
    }
  }


  function applyCandidateStructure() {

    const candidateRoot =
      document.getElementById(
        "candidate-signals-root"
      );

    if (!candidateRoot) return;


    const monitor =
      candidateRoot.querySelector(
        ".candidate-signals-monitor"
      );

    const analysis =
      candidateRoot.querySelector(
        ".candidate-signals-analysis"
      );

    const dossier =
      candidateRoot.querySelector(
        ".candidate-signals-dossier"
      );


    /*
     * Monitor becomes the dropdown.
     */

    if (monitor) {
      monitor.hidden =
        true;
    }


    /*
     * Both major analytical surfaces remain visible.
     *
     * Existing renderer order is:
     * Monitor -> Analysis -> Dossier.
     */

    if (analysis) {
      analysis.hidden =
        false;
    }


    if (dossier) {
      dossier.hidden =
        false;
    }
  }


  function restoreCandidateStructure() {

    const candidateRoot =
      document.getElementById(
        "candidate-signals-root"
      );

    if (!candidateRoot) return;


    [
      ".candidate-signals-monitor",
      ".candidate-signals-analysis",
      ".candidate-signals-dossier"
    ].forEach(
      selector => {

        const node =
          candidateRoot.querySelector(
            selector
          );

        if (node) {
          node.hidden =
            false;
        }
      }
    );
  }


  function removeTier3Controls() {

    hybridMount
      .querySelectorAll(
        [
          "[data-tier3-workspace-control]",
          "[data-tier3-candidate-control]",
          "[data-tier3-candidate-view-control]"
        ].join(", ")
      )
      .forEach(
        node =>
          node.remove()
      );
  }


  function applyTier3() {

    const active =
      tier3Query.matches;


    root.classList.toggle(
      "fr27-tier3-active",
      active
    );


    if (!active) {

      restoreCandidateStructure();

      removeTier3Controls();

      return;
    }


    /*
     * Remove the abandoned v2 Analysis/Dossier switch
     * if it survived a hot reload.
     */

    hybridMount
      .querySelectorAll(
        "[data-tier3-candidate-view-control]"
      )
      .forEach(
        node =>
          node.remove()
      );


    ensureWorkspaceControl();


    if (
      currentWorkspace() ===
      "candidates"
    ) {

      ensureCandidateControl();

      applyCandidateStructure();
    }
  }


  function queueRefresh() {

    if (refreshQueued) return;

    refreshQueued =
      true;


    requestAnimationFrame(
      () => {

        refreshQueued =
          false;

        applyTier3();
      }
    );
  }


  tier3Query.addEventListener(
    "change",
    queueRefresh
  );


  window.addEventListener(
    "hashchange",
    queueRefresh
  );


  const observer =
    new MutationObserver(
      queueRefresh
    );


  observer.observe(
    hybridMount,
    {
      childList: true,
      subtree: true
    }
  );


  queueRefresh();
})();

/* =========================================================
 * TIER 3 AGENDA CONTROLLER
 *
 * Reuse the original Agenda topic buttons as state owners.
 * Tier 3 exposes that state through one compact dropdown.
 * ========================================================= */
(() => {
  "use strict";

  const tier3Query =
    window.matchMedia(
      "(width < 1024px)"
    );

  const mount =
    document.getElementById(
      "hybrid-signal-board"
    );

  if (!mount) return;

  let refreshQueued = false;


  function removeAgendaTier3() {

    document
      .querySelector(
        ".fr27-tier3-agenda-selector"
      )
      ?.remove();

    document
      .querySelector(
        "#signal-agenda-panel .hybrid-agenda-v6-workspace"
      )
      ?.classList.remove(
        "fr27-tier3-agenda-workspace"
      );
  }


  function applyAgendaTier3() {

    const panel =
      document.getElementById(
        "signal-agenda-panel"
      );

    if (!panel) return;


    const workspace =
      panel.querySelector(
        ".hybrid-agenda-v6-workspace"
      );

    if (!workspace) return;


    if (!tier3Query.matches) {
      removeAgendaTier3();
      return;
    }


    workspace.classList.add(
      "fr27-tier3-agenda-workspace"
    );


    const monitor =
      workspace.querySelector(
        ".hybrid-agenda-v6-monitor"
      );

    if (!monitor) return;


    const topicButtons = [
      ...monitor.querySelectorAll(
        "[data-hybrid-agenda-topic]"
      )
    ];

    if (!topicButtons.length) return;


    let selectorRow =
      panel.querySelector(
        ".fr27-tier3-agenda-selector"
      );

    let select;


    if (!selectorRow) {

      selectorRow =
        document.createElement(
          "div"
        );

      selectorRow.className =
        "fr27-tier3-agenda-selector";


      const label =
        document.createElement(
          "span"
        );

      label.className =
        "fr27-tier3-control-label";

      label.textContent =
        "AGENDA MONITOR";


      const wrap =
        document.createElement(
          "div"
        );

      wrap.className =
        "fr27-tier3-select-wrap";


      select =
        document.createElement(
          "select"
        );

      select.className =
        "fr27-tier3-select";

      select.setAttribute(
        "aria-label",
        "Select Agenda topic"
      );


      wrap.append(select);

      selectorRow.append(
        label,
        wrap
      );


      select.addEventListener(
        "change",
        () => {

          const currentWorkspace =
            panel.querySelector(
              ".hybrid-agenda-v6-workspace"
            );

          if (!currentWorkspace) return;

          const selectedButton =
            currentWorkspace.querySelector(
              `[data-hybrid-agenda-topic="${
                CSS.escape(select.value)
              }"]`
            );

          /*
           * Preserve the original Agenda state path.
           * The real topic button remains the state owner.
           */
          selectedButton?.click();
        }
      );


      workspace.insertAdjacentElement(
        "beforebegin",
        selectorRow
      );

    } else {

      select =
        selectorRow.querySelector(
          "select"
        );
    }


    if (!select) return;


    /*
     * Rebuild options from the current original monitor.
     * This also keeps selection synchronized after rerenders.
     */
    const options =
      topicButtons.map(
        button => {

          const option =
            document.createElement(
              "option"
            );

          const topicId =
            button.dataset
              .hybridAgendaTopic;

          const name =
            button
              .querySelector(
                ".hybrid-agenda-v6-topic-name"
              )
              ?.textContent
              ?.trim() ||
            button.textContent.trim();

          const sourceDays =
            button
              .querySelector(
                ".hybrid-agenda-v6-topic-total strong"
              )
              ?.textContent
              ?.trim();

          const movement =
            String(
              button.dataset.movement ||
              ""
            )
              .trim()
              .toUpperCase();


          option.value =
            topicId || "";

          option.textContent = [
            name,
            movement,
            sourceDays
              ? `${sourceDays} source-days`
              : ""
          ]
            .filter(Boolean)
            .join(" · ");

          option.selected =
            button.getAttribute(
              "aria-pressed"
            ) === "true";

          return option;
        }
      );


    select.replaceChildren(
      ...options
    );
  }


  function queueAgendaRefresh() {

    if (refreshQueued) return;

    refreshQueued = true;

    requestAnimationFrame(
      () => {

        refreshQueued = false;

        applyAgendaTier3();
      }
    );
  }


  tier3Query.addEventListener(
    "change",
    queueAgendaRefresh
  );

  window.addEventListener(
    "hashchange",
    queueAgendaRefresh
  );


  const observer =
    new MutationObserver(
      queueAgendaRefresh
    );

  observer.observe(
    mount,
    {
      childList: true,
      subtree: true
    }
  );


  queueAgendaRefresh();
})();

/* =========================================================
 * TIER 3 ISSUES CONTROLLER
 *
 * Candidate-shell architecture:
 *
 *   WORKSPACE
 *   ISSUES MONITOR
 *   ISSUE EVOLUTION
 *   ISSUE DOSSIER
 *
 * Original policy-issue buttons remain the state owners.
 * ========================================================= */
(() => {
  "use strict";

  const tier3Query =
    window.matchMedia(
      "(width < 1024px)"
    );

  const mount =
    document.getElementById(
      "hybrid-signal-board"
    );

  if (!mount) return;

  let refreshQueued = false;


  function removeIssuesTier3() {

    document
      .querySelector(
        ".fr27-tier3-issues-selector"
      )
      ?.remove();

    document
      .querySelector(
        "#signal-issues-panel .hybrid-agenda-v6-workspace"
      )
      ?.classList.remove(
        "fr27-tier3-issues-workspace"
      );
  }


  function applyIssuesTier3() {

    const panel =
      document.getElementById(
        "signal-issues-panel"
      );

    if (!panel) return;


    const workspace =
      panel.querySelector(
        ".hybrid-agenda-v6-workspace"
      );

    if (!workspace) return;


    if (!tier3Query.matches) {
      removeIssuesTier3();
      return;
    }


    workspace.classList.add(
      "fr27-tier3-issues-workspace"
    );


    const monitor =
      workspace.querySelector(
        ".hybrid-agenda-v6-monitor"
      );

    if (!monitor) return;


    const issueButtons = [
      ...monitor.querySelectorAll(
        "[data-hybrid-policy-issue]"
      )
    ];

    if (!issueButtons.length) return;


    let selectorRow =
      panel.querySelector(
        ".fr27-tier3-issues-selector"
      );

    let select;


    if (!selectorRow) {

      selectorRow =
        document.createElement(
          "div"
        );

      /*
       * Reuse Candidate Monitor's actual Tier-3 shell class.
       * This guarantees exact visual parity.
       */
      selectorRow.className =
        "fr27-tier3-issues-selector fr27-tier3-candidate-control";


      const label =
        document.createElement(
          "span"
        );

      label.className =
        "fr27-tier3-control-label";

      label.textContent =
        "ISSUES MONITOR";


      const wrap =
        document.createElement(
          "div"
        );

      wrap.className =
        "fr27-tier3-select-wrap";


      select =
        document.createElement(
          "select"
        );

      select.className =
        "fr27-tier3-select";

      select.setAttribute(
        "aria-label",
        "Select policy issue"
      );


      wrap.append(select);

      selectorRow.append(
        label,
        wrap
      );


      select.addEventListener(
        "change",
        () => {

          const currentWorkspace =
            panel.querySelector(
              ".hybrid-agenda-v6-workspace"
            );

          const currentMonitor =
            currentWorkspace
              ?.querySelector(
                ".hybrid-agenda-v6-monitor"
              );

          if (!currentMonitor) return;


          const selectedButton =
            currentMonitor.querySelector(
              `[data-hybrid-policy-issue="${
                CSS.escape(select.value)
              }"]`
            );

          /*
           * Preserve the original Issues interaction/state
           * contract. The real monitor button owns selection.
           */
          selectedButton?.click();
        }
      );


      workspace.insertAdjacentElement(
        "beforebegin",
        selectorRow
      );

    } else {

      select =
        selectorRow.querySelector(
          "select"
        );
    }


    if (!select) return;


    const options =
      issueButtons.map(
        button => {

          const option =
            document.createElement(
              "option"
            );

          const issueId =
            button.dataset
              .hybridPolicyIssue;

          const name =
            button
              .querySelector(
                ".hybrid-agenda-v6-topic-name"
              )
              ?.textContent
              ?.trim() ||
            button.textContent.trim();

          const sourceDays =
            button
              .querySelector(
                ".hybrid-agenda-v6-topic-total strong"
              )
              ?.textContent
              ?.trim();

          const movement =
            String(
              button.dataset.movement ||
              ""
            )
              .trim()
              .toUpperCase();


          option.value =
            issueId || "";

          option.textContent = [
            name,
            movement,
            sourceDays
              ? `${sourceDays} source-days`
              : ""
          ]
            .filter(Boolean)
            .join(" · ");

          option.selected =
            button.getAttribute(
              "aria-pressed"
            ) === "true";

          return option;
        }
      );


    select.replaceChildren(
      ...options
    );
  }


  function queueIssuesRefresh() {

    if (refreshQueued) return;

    refreshQueued = true;

    requestAnimationFrame(
      () => {

        refreshQueued = false;

        applyIssuesTier3();
      }
    );
  }


  tier3Query.addEventListener(
    "change",
    queueIssuesRefresh
  );

  window.addEventListener(
    "hashchange",
    queueIssuesRefresh
  );


  const observer =
    new MutationObserver(
      queueIssuesRefresh
    );

  observer.observe(
    mount,
    {
      childList: true,
      subtree: true
    }
  );


  queueIssuesRefresh();
})();

/* TIER 3 EVENTS CONTROLLER — AUTHORITATIVE */
(() => {
  "use strict";

  const tier3Query =
    window.matchMedia(
      "(width < 1024px)"
    );

  const mount =
    document.getElementById(
      "hybrid-signal-board"
    );

  if (!mount) return;

  let refreshQueued = false;


  function removeEventsTier3() {

    document
      .querySelector(
        ".fr27-tier3-events-selector"
      )
      ?.remove();

    document
      .querySelector(
        "#signal-events-panel .hybrid-events-ops-main"
      )
      ?.classList.remove(
        "fr27-tier3-events-main"
      );
  }


  function applyEventsTier3() {

    const panel =
      document.getElementById(
        "signal-events-panel"
      );

    if (!panel) return;


    const main =
      panel.querySelector(
        ".hybrid-events-ops-main"
      );

    if (!main) return;


    if (!tier3Query.matches) {
      removeEventsTier3();
      return;
    }


    main.classList.add(
      "fr27-tier3-events-main"
    );


    const upcoming =
      main.querySelector(
        ".hybrid-events-upcoming"
      );

    if (!upcoming) return;


    const eventButtons = [
      ...upcoming.querySelectorAll(
        ".hybrid-events-upcoming-row[data-hybrid-event-id]"
      )
    ];

    if (!eventButtons.length) return;


    if (
      main.querySelector(
        ".fr27-tier3-events-selector"
      )
    ) {
      return;
    }


    const selectorRow =
      document.createElement("div");

    selectorRow.className =
      "fr27-tier3-events-selector";


    const label =
      document.createElement("div");

    label.className =
      "fr27-tier3-events-selector-label";

    label.textContent =
      "UPCOMING EVENTS";


    const select =
      document.createElement("select");

    select.className =
      "fr27-tier3-events-select";

    select.setAttribute(
      "aria-label",
      "Select upcoming campaign event"
    );


    eventButtons.forEach(button => {

      const option =
        document.createElement("option");

      const eventId =
        button.dataset.hybridEventId;

      const dateDay =
        button
          .querySelector("time strong")
          ?.textContent
          ?.trim() || "";

      const dateMonth =
        button
          .querySelector("time span")
          ?.textContent
          ?.trim() || "";

      const type =
        button
          .querySelector(
            ".hybrid-events-type-badge strong"
          )
          ?.textContent
          ?.trim() || "";

      const title =
        button
          .querySelector(
            ".hybrid-events-upcoming-copy > strong"
          )
          ?.textContent
          ?.trim() ||
        "Campaign event";


      option.value =
        eventId;

      option.textContent = [
        [dateDay, dateMonth]
          .filter(Boolean)
          .join(" "),
        type,
        title
      ]
        .filter(Boolean)
        .join(" · ");

      option.selected =
        button.getAttribute(
          "aria-pressed"
        ) === "true";

      select.append(option);
    });


    select.addEventListener(
      "change",
      () => {

        /*
         * Re-query after every render.
         * Selecting an event may replace the Events DOM.
         */
        const currentPanel =
          document.getElementById(
            "signal-events-panel"
          );

        const currentUpcoming =
          currentPanel?.querySelector(
            ".hybrid-events-upcoming"
          );

        const selectedButton =
          currentUpcoming?.querySelector(
            `.hybrid-events-upcoming-row[data-hybrid-event-id="${
              CSS.escape(select.value)
            }"]`
          );

        selectedButton?.click();
      }
    );


    selectorRow.append(
      label,
      select
    );


    /*
     * Exactly as Tier 2:
     * Upcoming selector belongs INSIDE ops-main.
     */
    main.prepend(
      selectorRow
    );
  }


  function queueEventsRefresh() {

    if (refreshQueued) return;

    refreshQueued = true;

    requestAnimationFrame(() => {
      refreshQueued = false;
      applyEventsTier3();
    });
  }


  const observer =
    new MutationObserver(
      queueEventsRefresh
    );

  observer.observe(
    mount,
    {
      childList: true,
      subtree: true
    }
  );


  tier3Query.addEventListener(
    "change",
    queueEventsRefresh
  );

  window.addEventListener(
    "hashchange",
    queueEventsRefresh
  );


  queueEventsRefresh();
})();
