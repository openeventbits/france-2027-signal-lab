(() => {
  "use strict";

  const shellLanguage = document.documentElement.lang.toLowerCase().startsWith("en") ? "en" : "fr";
  const localeTag = shellLanguage === "en" ? "en-GB" : "fr-FR";
  const formatNumber = value => new Intl.NumberFormat(localeTag).format(value);
  const shellText = (fr, en) => shellLanguage === "en" ? en : fr;

  const initClocks = () => {
    const election = new Date("2027-04-18T00:00:00+02:00");
    const countdown = document.querySelector("[data-countdown] .candidate-countdown-value");
    const hudCountdown = document.getElementById("fr27-hud-countdown-days");
    const refreshCountdown = () => {
      const days = Math.max(
        0,
        Math.ceil((election.getTime() - Date.now()) / 86400000)
      );
      if (countdown) countdown.textContent = formatNumber(days);
      if (hudCountdown) hudCountdown.textContent = formatNumber(days);
    };
    refreshCountdown();
    window.setInterval(refreshCountdown, 60000);
  };

  const initApplicationHud = () => {
    const hud = document.querySelector("#candidate-app-hud.fr27-app-hud");
    if (!hud) return;

    const shell = hud.closest(".polling-shell") || document.querySelector(".polling-shell");
    const toggle = hud.querySelector("#fr27-app-hud-toggle");
    const content = hud.querySelector(".fr27-app-hud-content");
    const emailToggle = hud.querySelector("#fr27-hud-email-toggle");
    const contactPopover = hud.querySelector("#fr27-hud-contact-popover");
    const contactCopy = hud.querySelector("#fr27-hud-contact-copy");
    const infoToggle = hud.querySelector("#fr27-hud-info-toggle");
    const infoPopover = hud.querySelector("#fr27-hud-info-popover");
    const root = document.body;
    if (!shell || !toggle || !content || !root) return;

    let expanded = true;

    const syncHudGeometry = () => {
      const rect = shell.getBoundingClientRect();
      const style = window.getComputedStyle(shell);
      const paddingLeft = Number.parseFloat(style.paddingLeft) || 0;
      const paddingRight = Number.parseFloat(style.paddingRight) || 0;
      const left = rect.left + paddingLeft;
      const width = Math.max(0, rect.width - paddingLeft - paddingRight);
      hud.style.setProperty("--fr27-app-hud-left", `${left.toFixed(2)}px`);
      hud.style.setProperty("--fr27-app-hud-width", `${width.toFixed(2)}px`);
    };

    const setInfoOpen = open => {
      if (!infoToggle || !infoPopover) return;
      infoToggle.setAttribute("aria-expanded", String(open));
      infoPopover.setAttribute("aria-hidden", String(!open));
    };
    const closeInfo = () => setInfoOpen(false);

    const setContactOpen = open => {
      if (!emailToggle || !contactPopover) return;
      emailToggle.setAttribute("aria-expanded", String(open));
      contactPopover.setAttribute("aria-hidden", String(!open));
    };
    const closeContact = () => setContactOpen(false);

    const renderHudState = () => {
      hud.dataset.expanded = expanded ? "true" : "false";
      root.classList.toggle("fr27-app-hud-collapsed", !expanded);
      toggle.setAttribute("aria-expanded", String(expanded));
      const label = expanded
        ? shellText("Réduire le dock système", "Collapse system dock")
        : shellText("Développer le dock système", "Expand system dock");
      toggle.setAttribute("aria-label", label);
      toggle.dataset.fr27Tooltip = label;
      content.setAttribute("aria-hidden", String(!expanded));
      if ("inert" in content) content.inert = !expanded;
      if (!expanded) {
        closeContact();
        closeInfo();
      }
    };

    const timeNode = hud.querySelector("#fr27-hud-paris-time");
    const dateNode = hud.querySelector("#fr27-hud-paris-date");
    const zoneNode = hud.querySelector("#fr27-hud-paris-zone");
    const timeFormatter = new Intl.DateTimeFormat(localeTag, {
      timeZone: "Europe/Paris",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23"
    });
    const dateFormatter = new Intl.DateTimeFormat(localeTag, {
      timeZone: "Europe/Paris",
      day: "2-digit",
      month: "short",
      year: "numeric"
    });
    const zoneFormatter = new Intl.DateTimeFormat(localeTag, {
      timeZone: "Europe/Paris",
      timeZoneName: "shortOffset"
    });

    const refreshParisClock = () => {
      if (!timeNode || !dateNode || !zoneNode) return;
      const now = new Date();
      timeNode.textContent = timeFormatter.format(now);
      timeNode.dateTime = now.toISOString();
      dateNode.textContent = dateFormatter
        .format(now)
        .replace(",", "")
        .toLocaleUpperCase(localeTag);
      const zonePart = zoneFormatter
        .formatToParts(now)
        .find(part => part.type === "timeZoneName");
      if (zonePart) {
        zoneNode.textContent = zonePart.value
          .replace("UTC+", "UTC+")
          .replace("UTC−", "UTC-")
          .replace("GMT+", "UTC+")
          .replace("GMT-", "UTC-")
          .replace("GMT", "UTC");
      }
    };

    refreshParisClock();
    window.setInterval(refreshParisClock, 1000);

    toggle.addEventListener("click", () => {
      expanded = !expanded;
      renderHudState();
    });

    if (emailToggle && contactPopover) {
      emailToggle.addEventListener("click", event => {
        event.stopPropagation();
        const open = emailToggle.getAttribute("aria-expanded") === "true";
        closeInfo();
        setContactOpen(!open);
      });
      contactPopover.addEventListener("click", event => event.stopPropagation());
    }

    if (contactCopy) {
      contactCopy.addEventListener("click", async () => {
        const address = "contact@france2027.app";
        try {
          if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(address);
          } else {
            const field = document.createElement("textarea");
            field.value = address;
            field.setAttribute("readonly", "");
            field.style.position = "fixed";
            field.style.opacity = "0";
            document.body.append(field);
            field.select();
            document.execCommand("copy");
            field.remove();
          }
          contactCopy.textContent = shellText("COPIÉE", "COPIED");
          window.setTimeout(() => { contactCopy.textContent = shellText("COPIER L’ADRESSE", "COPY ADDRESS"); }, 1600);
        } catch (_) {
          contactCopy.textContent = shellText("ÉCHEC DE LA COPIE", "COPY FAILED");
          window.setTimeout(() => { contactCopy.textContent = shellText("COPIER L’ADRESSE", "COPY ADDRESS"); }, 1600);
        }
      });
    }

    if (infoToggle && infoPopover) {
      infoToggle.addEventListener("click", event => {
        event.stopPropagation();
        const open = infoToggle.getAttribute("aria-expanded") === "true";
        closeContact();
        setInfoOpen(!open);
      });
      infoPopover.addEventListener("click", event => event.stopPropagation());
    }

    document.addEventListener("click", () => {
      closeContact();
      closeInfo();
    });

    window.addEventListener("keydown", event => {
      if (event.key !== "Escape") return;
      if (emailToggle?.getAttribute("aria-expanded") === "true") {
        closeContact();
        emailToggle.focus({ preventScroll: true });
        return;
      }
      if (infoToggle?.getAttribute("aria-expanded") === "true") {
        closeInfo();
        infoToggle.focus({ preventScroll: true });
        return;
      }
      if (expanded) {
        expanded = false;
        renderHudState();
        toggle.focus({ preventScroll: true });
      }
    });

    renderHudState();
    syncHudGeometry();
    window.addEventListener("resize", syncHudGeometry, { passive: true });
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(syncHudGeometry);
      observer.observe(shell);
    }
  };

  const initStandaloneShell = () => {
    initClocks();
    initApplicationHud();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initStandaloneShell, { once: true });
  } else {
    initStandaloneShell();
  }
})();


/* FR27 POLL DETAIL PHASE 2 — SCENARIO NAVIGATION */
(() => {
  "use strict";

  const scenarios = Array.from(
    document.querySelectorAll(".poll-detail-scenario")
  );

  if (!scenarios.length) return;

  const navigationLinks = Array.from(
    document.querySelectorAll("[data-scenario-target]")
  );

  const expandAll = document.querySelector("[data-poll-expand-all]");
  const collapseAll = document.querySelector("[data-poll-collapse-all]");

  const syncScenarioLabel = details => {
    const label = details.querySelector(
      ".poll-detail-scenario-toggle-text"
    );

    if (!label) return;

    label.textContent = details.open
      ? label.dataset.closeLabel
      : label.dataset.openLabel;
  };

  const setActiveScenario = id => {
    for (const link of navigationLinks) {
      const active = link.dataset.scenarioTarget === id;
      link.classList.toggle("is-active", active);

      if (active) {
        link.setAttribute("aria-current", "true");
      } else {
        link.removeAttribute("aria-current");
      }
    }
  };

  const openScenario = (
    details,
    {
      updateHash = false,
      scroll = false
    } = {}
  ) => {
    if (!details) return;

    details.open = true;
    syncScenarioLabel(details);
    setActiveScenario(details.id);

    if (updateHash) {
      const nextHash = `#${details.id}`;

      if (window.location.hash !== nextHash) {
        window.history.replaceState(
          null,
          "",
          nextHash
        );
      }
    }

    if (scroll) {
      window.requestAnimationFrame(() => {
        details.scrollIntoView({
          behavior: "smooth",
          block: "start"
        });
      });
    }
  };

  for (const details of scenarios) {
    syncScenarioLabel(details);

    details.addEventListener("toggle", () => {
      syncScenarioLabel(details);

      if (details.open) {
        setActiveScenario(details.id);
      }
    });
  }

  for (const link of navigationLinks) {
    link.addEventListener("click", event => {
      const id = link.dataset.scenarioTarget;
      const target = id ? document.getElementById(id) : null;

      if (!target) return;

      event.preventDefault();

      openScenario(target, {
        updateHash: true,
        scroll: true
      });
    });
  }

  if (expandAll) {
    expandAll.addEventListener("click", () => {
      for (const details of scenarios) {
        details.open = true;
        syncScenarioLabel(details);
      }
    });
  }

  if (collapseAll) {
    collapseAll.addEventListener("click", () => {
      for (const details of scenarios) {
        details.open = false;
        syncScenarioLabel(details);
      }

      for (const link of navigationLinks) {
        link.classList.remove("is-active");
        link.removeAttribute("aria-current");
      }
    });
  }

  const openFromHash = ({ scroll = false } = {}) => {
    const hash = window.location.hash.replace(/^#/, "");

    if (!/^scenario-\d+$/.test(hash)) return;

    const target = document.getElementById(hash);

    if (!target) return;

    openScenario(target, {
      updateHash: false,
      scroll
    });
  };

  openFromHash();

  window.addEventListener("hashchange", () => {
    openFromHash({ scroll: true });
  });
})();

/* FR27 POLL DETAIL — POLLSTER NOTE TOOLTIP */
(() => {
  "use strict";

  const trigger = document.querySelector(
    "[data-poll-tooltip-trigger]"
  );

  if (!trigger) return;

  const wrapper = trigger.closest(
    ".poll-detail-tooltip-wrap"
  );

  if (!wrapper) return;

  const setOpen = open => {
    wrapper.dataset.open = open ? "true" : "false";
    trigger.setAttribute(
      "aria-expanded",
      String(open)
    );
  };

  trigger.addEventListener("click", event => {
    event.stopPropagation();

    const open =
      wrapper.dataset.open === "true";

    setOpen(!open);
  });

  document.addEventListener("click", event => {
    if (wrapper.contains(event.target)) return;
    setOpen(false);
  });

  window.addEventListener(
    "keydown",
    event => {
      if (
        event.key !== "Escape" ||
        wrapper.dataset.open !== "true"
      ) {
        return;
      }

      setOpen(false);

      trigger.focus({
        preventScroll: true
      });

      event.stopImmediatePropagation();
    },
    true
  );
})();
