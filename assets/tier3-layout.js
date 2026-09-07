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
