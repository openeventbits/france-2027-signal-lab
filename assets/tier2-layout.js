/* FR27 Tier 2 prototype — 1024px <= width < 1399px
   Reuses the existing Media Pulse and Candidate renderers.
   No data contracts, writers, routes, or publication logic are changed. */
const fr27Tier2T = (key, fallback) =>
  window.FR27I18N?.t?.(key, null, fallback) ?? fallback;
(() => {
  "use strict";

  const tier2Query = window.matchMedia(
    "(1024px <= width < 1399px)"
  );

  const tier3Query = window.matchMedia(
    "(width < 1024px)"
  );

  const root = document.documentElement;
  const heroGrid = document.querySelector(".hero-grid");
  const contextStrip = document.querySelector(".context-strip");
  const mediaPanel = document.querySelector(".top-media-pulse");
  const mediaMount = document.getElementById("top-media-pulse-content");
  const hybridMount = document.getElementById("hybrid-signal-board");

  if (
    !heroGrid ||
    !contextStrip ||
    !mediaPanel ||
    !mediaMount ||
    !hybridMount
  ) {
    return;
  }

  const workspaceHashes = Object.freeze({
    candidates: "#signal-candidates",
    agenda: "#signal-agenda",
    events: "#signal-events",
    issues: "#signal-issues",
    runoff: "#signal-runoff"
  });

  const workspaceLabels = Object.freeze({
    candidates: fr27Tier2T("signal_board.candidates_847367c6", "CANDIDATES"),
    agenda: fr27Tier2T("signal_board.agenda", "AGENDA"),
    events: fr27Tier2T("signal_board.events", "EVENTS"),
    issues: fr27Tier2T("signal_board.issues", "ISSUES"),
    runoff: fr27Tier2T("signal_board.runoff", "RUNOFF")
  });

  const mediaHome = document.createComment(
    "FR27 Tier 2 Media Pulse home"
  );
  mediaPanel.parentNode.insertBefore(mediaHome, mediaPanel);

  let mediaRow = null;
  let mediaViewBeforeTier2 = "overview";

  /*
   * TIER 2 MEDIA STATE OWNERSHIP FIX
   *
   * Tier 2 may restore the remembered tab once when it is
   * exited, but must not continuously reassert that state
   * while Tier 3 or Tier 1 owns Media Pulse.
   */
  let tier2WasActive = tier2Query.matches;

  let refreshQueued = false;

  function currentWorkspace() {
    const match = Object.entries(workspaceHashes).find(
      ([, hash]) => hash === window.location.hash
    );
    return match ? match[0] : "candidates";
  }

  function createSelectControl(className, labelText, selectLabel) {
    const control = document.createElement("div");
    control.className =
      `fr27-tier2-control ${className}`;

    const label = document.createElement("span");
    label.className = "fr27-tier2-control-label";
    label.textContent = labelText;

    const wrap = document.createElement("div");
    wrap.className = "fr27-tier2-select-wrap";

    const select = document.createElement("select");
    select.className = "fr27-tier2-select";
    select.setAttribute("aria-label", selectLabel);

    wrap.append(select);
    control.append(label, wrap);

    return { control, select };
  }

  function ensureMediaRow() {
    if (mediaRow?.isConnected) return mediaRow;

    mediaRow = document.createElement("section");
    mediaRow.className = "fr27-tier2-media-row";
    mediaRow.setAttribute("aria-label", "Media Pulse");

    contextStrip.insertAdjacentElement("afterend", mediaRow);
    return mediaRow;
  }

  function rememberMediaView() {
    const selected = mediaMount.querySelector(
      '[data-top-media-tab][aria-selected="true"]'
    );
    if (selected?.dataset.topMediaTab) {
      mediaViewBeforeTier2 = selected.dataset.topMediaTab;
    }
  }

  function showDualMedia() {
    const dashboard = mediaMount.querySelector(".top-media-dashboard");
    if (!dashboard) return;

    dashboard.dataset.tier2DualMedia = "true";

    mediaMount
      .querySelectorAll("[data-top-media-panel]")
      .forEach(panel => {
        panel.hidden = false;
        panel.style.display = "";
        panel.classList.add("is-active");
        panel.setAttribute("aria-hidden", "false");
      });
  }

  function restoreTabbedMedia() {
    const dashboard = mediaMount.querySelector(".top-media-dashboard");
    if (!dashboard) return;

    delete dashboard.dataset.tier2DualMedia;

    const requested =
      mediaViewBeforeTier2 === "coverage"
        ? "coverage"
        : "overview";

    mediaMount
      .querySelectorAll("[data-top-media-tab]")
      .forEach(tab => {
        const selected =
          tab.dataset.topMediaTab === requested;
        tab.classList.toggle("is-active", selected);
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
      });

    mediaMount
      .querySelectorAll("[data-top-media-panel]")
      .forEach(panel => {
        const selected =
          panel.dataset.topMediaPanel === requested;
        panel.classList.toggle("is-active", selected);
        panel.hidden = !selected;
        panel.style.display = selected ? "" : "none";
        panel.setAttribute("aria-hidden", String(!selected));
      });
  }

  function moveMediaIntoTier2() {
    const row = ensureMediaRow();
    if (mediaPanel.parentNode !== row) {
      rememberMediaView();
      row.append(mediaPanel);
    }
    showDualMedia();
  }

  function restoreMediaOutsideTier2(restoreView = true) {
    /*
     * Only restore the remembered tab on an actual transition
     * out of Tier 2. Repeated inactive refreshes must not reset
     * a tab chosen by the Tier-3 user.
     */
    if (restoreView) {
      restoreTabbedMedia();
    }

    if (tier3Query.matches) {
      contextStrip.insertAdjacentElement(
        "afterend",
        mediaPanel
      );
    } else if (mediaHome.parentNode) {
      mediaHome.parentNode.insertBefore(
        mediaPanel,
        mediaHome.nextSibling
      );
    }

    mediaRow?.remove();
    mediaRow = null;
  }

  function ensureWorkspaceControl() {
    const workspace = hybridMount.querySelector(
      ".hybrid-workspace"
    );
    if (!workspace) return;

    let control = workspace.querySelector(
      "[data-tier2-workspace-control]"
    );

    let select;

    if (!control) {
      const created = createSelectControl(
        "fr27-tier2-workspace-control",
        fr27Tier2T("responsive.workspace", "WORKSPACE"),
        fr27Tier2T("responsive.workspace_aria", "Choose FR27 workspace")
      );

      control = created.control;
      select = created.select;
      control.dataset.tier2WorkspaceControl = "";

      Object.keys(workspaceHashes).forEach(key => {
        const option = document.createElement("option");
        option.value = key;
        option.textContent = workspaceLabels[key];
        select.append(option);
      });

      select.addEventListener("change", () => {
        const key = select.value;
        const hash = workspaceHashes[key];
        if (!hash) return;

        if (window.location.hash === hash) {
          window.hybridDashboard?.setActiveSignalView?.(key);
        } else {
          window.location.hash = hash;
        }
      });

      workspace.insertBefore(control, workspace.firstChild);
    } else {
      select = control.querySelector("select");
    }

    if (select) {
      select.value = currentWorkspace();
    }
  }

  function candidateButtons(rootNode) {
    return [
      ...rootNode.querySelectorAll(
        ".candidate-signals-candidate-button"
      )
    ];
  }

  function candidateOptionLabel(button) {
    const name =
      button.querySelector(".candidate-signals-candidate-name")
        ?.textContent?.trim() || fr27Tier2T("responsive.unknown_candidate", "Candidate");

    const poll =
      button.querySelector(".candidate-signals-candidate-poll")
        ?.textContent?.trim() || "";

    const tierCode =
        String(button.dataset.candidateTier || "")
          .trim()
          .toLowerCase();

      const tierKey =
        tierCode === "primary"
          ? "main"
          : tierCode;

      const tier =
        tierKey
          ? fr27Tier2T(
              `candidate.tier.${tierKey}`,
              tierCode.toUpperCase()
            ).toUpperCase()
          : "";

    return [name, tier, poll].filter(Boolean).join(" · ");
  }

  function ensureCandidateControl() {
    const panel = document.getElementById(
      "signal-candidates-panel"
    );
    const candidateRoot = document.getElementById(
      "candidate-signals-root"
    );

    if (!panel || !candidateRoot) return;

    let control = panel.querySelector(
      "[data-tier2-candidate-control]"
    );

    let select;

    if (!control) {
      const created = createSelectControl(
        "fr27-tier2-candidate-control",
        fr27Tier2T("candidate.candidate_monitor", "CANDIDATE MONITOR"),
        fr27Tier2T("responsive.candidate_aria", "Choose candidate")
      );

      control = created.control;
      select = created.select;
      control.dataset.tier2CandidateControl = "";

      select.addEventListener("change", () => {
        const candidateId = select.value;
        const currentRoot = document.getElementById(
          "candidate-signals-root"
        );
        if (!currentRoot) return;

        const target = candidateButtons(currentRoot).find(
          button =>
            button.dataset.candidateSignalsCandidate ===
            candidateId
        );

        target?.click();
        queueRefresh();
      });

      panel.insertBefore(control, candidateRoot);
    } else {
      select = control.querySelector("select");
    }

    if (!select) return;

    const buttons = candidateButtons(candidateRoot);

    if (!buttons.length) {
      if (select.dataset.optionSignature !== "loading") {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = fr27Tier2T("responsive.loading_candidates", "Loading candidates…");
        select.replaceChildren(option);
        select.disabled = true;
        select.dataset.optionSignature = "loading";
      }
      return;
    }

    const signature = buttons
      .map(button =>
        [
          button.dataset.candidateSignalsCandidate,
          candidateOptionLabel(button)
        ].join(":")
      )
      .join("|");

    if (select.dataset.optionSignature !== signature) {
      const options = buttons.map(button => {
        const option = document.createElement("option");
        option.value =
          button.dataset.candidateSignalsCandidate || "";
        option.textContent = candidateOptionLabel(button);
        return option;
      });

      select.replaceChildren(...options);
      select.dataset.optionSignature = signature;
      select.disabled = false;
    }

    const selected = buttons.find(
      button => button.getAttribute("aria-pressed") === "true"
    );

    if (selected?.dataset.candidateSignalsCandidate) {
      select.value =
        selected.dataset.candidateSignalsCandidate;
    }
  }

  function removeTier2Controls() {
    hybridMount
      .querySelectorAll(
        "[data-tier2-workspace-control], [data-tier2-candidate-control]"
      )
      .forEach(node => node.remove());
  }

  function applyTier2() {
    const active = tier2Query.matches;
    root.classList.toggle("fr27-tier2-active", active);

    if (!active) {
      /*
       * Restore the remembered tab only on the boundary
       * crossing out of Tier 2.
       *
       * Once Tier 3 is active, its Overview/Coverage choice
       * must survive unrelated MutationObserver refreshes.
       */
      restoreMediaOutsideTier2(tier2WasActive);

      tier2WasActive = false;

      removeTier2Controls();
      return;
    }

    tier2WasActive = true;

    moveMediaIntoTier2();
    ensureWorkspaceControl();
    ensureCandidateControl();
  }

  function queueRefresh() {
    if (refreshQueued) return;
    refreshQueued = true;

    requestAnimationFrame(() => {
      refreshQueued = false;
      applyTier2();
    });
  }

  tier2Query.addEventListener("change", queueRefresh);
  tier3Query.addEventListener("change", queueRefresh);
  window.addEventListener("hashchange", queueRefresh);

  const hybridObserver = new MutationObserver(queueRefresh);
  hybridObserver.observe(hybridMount, {
    childList: true,
    subtree: true
  });

  const mediaObserver = new MutationObserver(queueRefresh);
  mediaObserver.observe(mediaMount, {
    childList: true,
    subtree: false
  });

  queueRefresh();
})();

/* TIER 2 AGENDA CONTROLLER */
(() => {
  "use strict";

  const tier2Query = window.matchMedia(
    "(1024px <= width < 1399px)"
  );

  const mount =
    document.getElementById("hybrid-signal-board");

  if (!mount) return;

  let refreshQueued = false;

  function removeAgendaTier2() {
    document
      .querySelector(".fr27-tier2-agenda-selector")
      ?.remove();

    document
      .querySelector(
        "#signal-agenda-panel .hybrid-agenda-v6-workspace"
      )
      ?.classList.remove(
        "fr27-tier2-agenda-workspace"
      );
  }

  function applyAgendaTier2() {
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

    if (!tier2Query.matches) {
      removeAgendaTier2();
      return;
    }

    workspace.classList.add(
      "fr27-tier2-agenda-workspace"
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

    /*
     * renderAll() replaces the Agenda workspace
     * whenever the selected topic changes.
     * Therefore recreate the selector only when
     * the current render does not already have one.
     */

    if (
      panel.querySelector(
        ".fr27-tier2-agenda-selector"
      )
    ) {
      return;
    }

    const selectorRow =
      document.createElement("div");

    selectorRow.className =
      "fr27-tier2-agenda-selector";

    const label =
      document.createElement("div");

    label.className =
      "fr27-tier2-agenda-selector-label";

    label.textContent =
      fr27Tier2T("agenda_workspace.monitor", "AGENDA MONITOR");

    const select =
      document.createElement("select");

    select.className =
      "fr27-tier2-agenda-select";

    select.setAttribute(
      "aria-label",
      fr27Tier2T("responsive.agenda_aria", "Select Agenda topic")
    );

    topicButtons.forEach(button => {
      const option =
        document.createElement("option");

      const topicId =
        button.dataset.hybridAgendaTopic;

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

      const movementCode =
        String(button.dataset.movement || "")
          .trim()
          .toLowerCase();

      const movement =
        movementCode
          ? fr27Tier2T(
              `agenda_workspace.movement.${movementCode}`,
              movementCode.toUpperCase()
            )
          : "";

      option.value = topicId;

      option.textContent = [
        name,
        movement,
        sourceDays
          ? `${sourceDays} ${fr27Tier2T("responsive.source_days", "source-days")}`
          : ""
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
        const selectedButton =
          workspace.querySelector(
            `[data-hybrid-agenda-topic="${
              CSS.escape(select.value)
            }"]`
          );

        /*
         * Reuse the existing Agenda click path.
         * That path updates selectedAgendaTopicId
         * and triggers the normal dashboard render.
         */
        selectedButton?.click();
      }
    );

    selectorRow.append(
      label,
      select
    );

    workspace.insertAdjacentElement(
      "beforebegin",
      selectorRow
    );
  }

  function queueAgendaRefresh() {
    if (refreshQueued) return;

    refreshQueued = true;

    requestAnimationFrame(() => {
      refreshQueued = false;
      applyAgendaTier2();
    });
  }

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

  tier2Query.addEventListener(
    "change",
    queueAgendaRefresh
  );

  queueAgendaRefresh();
})();

/* TIER 2 ISSUES CONTROLLER */
(() => {
  "use strict";

  const tier2Query =
    window.matchMedia(
      "(1024px <= width < 1399px)"
    );

  const mount =
    document.getElementById(
      "hybrid-signal-board"
    );

  if (!mount) return;

  let refreshQueued = false;


  function removeIssuesTier2() {

    document
      .querySelector(
        ".fr27-tier2-issues-selector"
      )
      ?.remove();

    document
      .querySelector(
        "#signal-issues-panel .hybrid-agenda-v6-workspace"
      )
      ?.classList.remove(
        "fr27-tier2-issues-workspace"
      );
  }


  function applyIssuesTier2() {

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


    if (!tier2Query.matches) {
      removeIssuesTier2();
      return;
    }


    workspace.classList.add(
      "fr27-tier2-issues-workspace"
    );


    /*
     * Existing Policy Monitor owns the real issue buttons.
     */

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


    /*
     * renderAll() replaces the Issues workspace when the
     * selected issue changes, so do not duplicate the row
     * within one render.
     */

    if (
      panel.querySelector(
        ".fr27-tier2-issues-selector"
      )
    ) {
      return;
    }


    const selectorRow =
      document.createElement("div");

    selectorRow.className =
      "fr27-tier2-issues-selector";


    const label =
      document.createElement("div");

    label.className =
      "fr27-tier2-issues-selector-label";

    label.textContent =
      fr27Tier2T("policy_workspace.monitor", "POLICY MONITOR");


    const select =
      document.createElement("select");

    select.className =
      "fr27-tier2-issues-select";

    select.setAttribute(
      "aria-label",
      fr27Tier2T("responsive.issues_aria", "Select policy issue")
    );


    issueButtons.forEach(button => {

      const option =
        document.createElement("option");


      const issueId =
        button.dataset.hybridPolicyIssue;


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


      const movementCode =
        String(button.dataset.movement || "")
          .trim()
          .toLowerCase();

      const movement =
        movementCode
          ? fr27Tier2T(
              `agenda_workspace.movement.${movementCode}`,
              movementCode.toUpperCase()
            )
          : "";


      option.value =
        issueId;


      option.textContent = [
        name,
        movement,
        sourceDays
          ? `${sourceDays} ${fr27Tier2T("responsive.source_days", "source-days")}`
          : ""
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

        const selectedButton =
          workspace.querySelector(
            `[data-hybrid-policy-issue="${
              CSS.escape(select.value)
            }"]`
          );

        /*
         * Reuse the existing Policy Issues click path.
         */

        selectedButton?.click();
      }
    );


    selectorRow.append(
      label,
      select
    );


    workspace.insertAdjacentElement(
      "beforebegin",
      selectorRow
    );
  }


  function queueIssuesRefresh() {

    if (refreshQueued) return;

    refreshQueued = true;

    requestAnimationFrame(() => {
      refreshQueued = false;
      applyIssuesTier2();
    });
  }


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


  tier2Query.addEventListener(
    "change",
    queueIssuesRefresh
  );


  queueIssuesRefresh();
})();

/* TIER 2 EVENTS CONTROLLER V2 */
(() => {
  "use strict";

  const tier2Query =
    window.matchMedia(
      "(1024px <= width < 1399px)"
    );

  const mount =
    document.getElementById(
      "hybrid-signal-board"
    );

  if (!mount) return;

  let refreshQueued = false;


  function removeEventsTier2() {

    document
      .querySelector(
        ".fr27-tier2-events-selector"
      )
      ?.remove();

    document
      .querySelector(
        "#signal-events-panel .hybrid-events-ops-main"
      )
      ?.classList.remove(
        "fr27-tier2-events-main"
      );
  }


  function applyEventsTier2() {

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


    if (!tier2Query.matches) {
      removeEventsTier2();
      return;
    }


    main.classList.add(
      "fr27-tier2-events-main"
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
        ".fr27-tier2-events-selector"
      )
    ) {
      return;
    }


    const selectorRow =
      document.createElement("div");

    selectorRow.className =
      "fr27-tier2-events-selector";


    const label =
      document.createElement("div");

    label.className =
      "fr27-tier2-events-selector-label";

    label.textContent =
      fr27Tier2T("events_workspace.upcoming_events", "UPCOMING EVENTS");


    const select =
      document.createElement("select");

    select.className =
      "fr27-tier2-events-select";

    select.setAttribute(
      "aria-label",
      fr27Tier2T("responsive.events_aria", "Select upcoming campaign event")
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
          ?.trim() || fr27Tier2T("responsive.campaign_event", "Campaign event");


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

        const selectedButton =
          upcoming.querySelector(
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
     * CRITICAL:
     * selector belongs INSIDE ops-main.
     *
     * Do not insert it as another child of
     * .hybrid-events-workspace.
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
      applyEventsTier2();
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


  tier2Query.addEventListener(
    "change",
    queueEventsRefresh
  );


  queueEventsRefresh();
})();
