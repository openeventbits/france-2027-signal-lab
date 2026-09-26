/* === FR27 STANDALONE SHELL: current-main Polling Lab behavior for candidate pages === */
(() => {
  "use strict";

  const shellLanguage = document.documentElement.lang.toLowerCase().startsWith("en") ? "en" : "fr";
  const localeTag = shellLanguage === "en" ? "en-GB" : "fr-FR";
  const formatInteger = value => new Intl.NumberFormat(localeTag).format(value);
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
      if (countdown) countdown.textContent = formatInteger(days);
      if (hudCountdown) hudCountdown.textContent = formatInteger(days);
    };
    refreshCountdown();
    window.setInterval(refreshCountdown, 60000);
  };

  const loadHudPollCount = async () => {
    const hudPollsValue = document.getElementById("fr27-hud-polls-value");
    if (!hudPollsValue) return;

    try {
      const response = await fetch("/poll_explorer.json", {
        cache: "no-store",
        credentials: "same-origin"
      });
      if (!response.ok) return;
      const payload = await response.json();
      const metrics = payload?.metrics;
      if (
        !metrics ||
        !Number.isFinite(metrics.wave_count) ||
        !Number.isInteger(metrics.wave_count) ||
        metrics.wave_count < 0
      ) return;
      hudPollsValue.textContent = formatInteger(metrics.wave_count);
    } catch (_) {
      // The semantic placeholder remains visible when the explorer is unavailable.
    }
  };

  const initApplicationHud = () => {
    const hud = document.querySelector("#candidate-app-hud.fr27-app-hud");
    if (!hud) return;

    const shell = hud.closest(".candidate-shell") || document.querySelector(".candidate-shell");
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
    void loadHudPollCount();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initStandaloneShell, { once: true });
  } else {
    initStandaloneShell();
  }
})();
/* === END FR27 STANDALONE SHELL === */
