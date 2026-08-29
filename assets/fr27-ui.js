(() => {
  "use strict";

  const tooltipSelector = "[data-fr27-tooltip]";
  const tooltipId = "fr27-shared-tooltip";
  const showDelay = 140;
  const viewportGap = 10;
  let activeTrigger = null;
  let showTimer = 0;
  let tooltip = null;

  function ensureTooltip() {
    if (tooltip?.isConnected) return tooltip;
    tooltip = document.createElement("div");
    tooltip.id = tooltipId;
    tooltip.className = "fr27-tooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.setAttribute("aria-hidden", "true");
    document.body.append(tooltip);
    return tooltip;
  }

  function describedBy(trigger, add) {
    const ids = String(trigger.getAttribute("aria-describedby") || "")
      .split(/\s+/)
      .filter(Boolean)
      .filter(id => id !== tooltipId);
    if (add) ids.push(tooltipId);
    if (ids.length) trigger.setAttribute("aria-describedby", ids.join(" "));
    else trigger.removeAttribute("aria-describedby");
  }

  function position(trigger) {
    const node = ensureTooltip();
    const triggerRect = trigger.getBoundingClientRect();
    const tooltipRect = node.getBoundingClientRect();
    const below = triggerRect.bottom + 8;
    const above = triggerRect.top - tooltipRect.height - 8;
    const top = below + tooltipRect.height <= window.innerHeight - viewportGap || above < viewportGap
      ? below
      : above;
    const idealLeft = triggerRect.left + (triggerRect.width - tooltipRect.width) / 2;
    const rightEdgeInset = trigger.id === "masthead-countdown" ? 24 : 0;
    const left = Math.max(
      viewportGap,
      Math.min(
        idealLeft,
        window.innerWidth - tooltipRect.width - viewportGap - rightEdgeInset
      )
    );
    node.style.left = `${Math.round(left)}px`;
    node.style.top = `${Math.round(Math.max(viewportGap, top))}px`;
  }

  function show(trigger) {
    const text = String(trigger?.dataset.fr27Tooltip || "").trim();
    if (
      !text ||
      !trigger.isConnected ||
      trigger.getAttribute("aria-expanded") === "true"
    ) return;
    const node = ensureTooltip();
    if (activeTrigger && activeTrigger !== trigger) describedBy(activeTrigger, false);
    activeTrigger = trigger;
    node.textContent = text;
    node.setAttribute("aria-hidden", "false");
    describedBy(trigger, true);
    node.classList.add("is-visible");
    position(trigger);
  }

  function schedule(trigger) {
    window.clearTimeout(showTimer);
    showTimer = window.setTimeout(() => show(trigger), showDelay);
  }

  function hide(trigger = activeTrigger) {
    window.clearTimeout(showTimer);
    showTimer = 0;
    if (trigger) describedBy(trigger, false);
    if (trigger && activeTrigger && trigger !== activeTrigger) return;
    activeTrigger = null;
    if (!tooltip) return;
    tooltip.classList.remove("is-visible");
    tooltip.setAttribute("aria-hidden", "true");
  }

  function closestTrigger(target) {
    return target instanceof Element ? target.closest(tooltipSelector) : null;
  }

  document.addEventListener("pointerover", event => {
    if (event.pointerType === "touch") return;
    const trigger = closestTrigger(event.target);
    if (!trigger || trigger.contains(event.relatedTarget)) return;
    schedule(trigger);
  });

  document.addEventListener("pointerout", event => {
    const trigger = closestTrigger(event.target);
    if (!trigger || trigger.contains(event.relatedTarget)) return;
    hide(trigger);
  });

  document.addEventListener("focusin", event => {
    const trigger = closestTrigger(event.target);
    if (trigger) schedule(trigger);
  });

  document.addEventListener("focusout", event => {
    const trigger = closestTrigger(event.target);
    if (trigger && !trigger.contains(event.relatedTarget)) hide(trigger);
  });

  document.addEventListener("pointerdown", () => {
    if (activeTrigger) hide();
  }, true);

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") hide();
  });

  window.addEventListener("resize", () => activeTrigger ? position(activeTrigger) : null);
  window.addEventListener("scroll", () => activeTrigger ? position(activeTrigger) : null, true);

  const block = (width = "100%", height = "9px", extra = "") =>
    `<span class="fr27-skeleton-block${extra ? ` ${extra}` : ""}" style="--fr27-skeleton-width:${width};--fr27-skeleton-height:${height}"></span>`;
  const circle = (size = "28px") =>
    `<span class="fr27-skeleton-circle" style="--fr27-skeleton-size:${size}"></span>`;
  const copy = (wide = "82%", short = "45%") =>
    `<span class="fr27-skeleton-row-copy">${block(wide)}${block(short, "7px")}</span>`;
  const row = (index = 0, portrait = false) =>
    `<span class="fr27-skeleton-row">${portrait ? circle() : block("42px", "15px", "fr27-skeleton-source")}${copy(index % 2 ? "72%" : "88%", index % 3 ? "38%" : "52%")}</span>`;

  function skeletonMarkup(pattern = "list") {
    if (pattern === "briefing") {
      return `<div class="fr27-skeleton-briefing">${[0, 1, 2].map(index => row(index)).join("")}</div>`;
    }
    if (pattern === "race") {
      return `<div class="fr27-skeleton-race">${[0, 1, 2, 3, 4].map(index => `<span class="fr27-skeleton-row">${circle()}${block(index % 2 ? "72%" : "88%")} ${block("100%", "7px")}${block("30px", "12px")}</span>`).join("")}</div>`;
    }
    if (pattern === "metrics") {
      return `<div class="fr27-skeleton-metrics">${[0, 1, 2, 3].map(() => `<span class="fr27-skeleton-metric">${block("42px", "15px")}${block("54px", "7px")}</span>`).join("")}</div>`;
    }
    if (pattern === "media") {
      return `<div class="fr27-skeleton-media">${[0, 1, 2, 3, 4].map(index => `<span class="fr27-skeleton-row">${block("14px", "12px")}${block(index % 2 ? "72%" : "88%")} ${block("100%", "7px")}${block("30px", "10px")}</span>`).join("")}</div>`;
    }
    if (["workspace", "candidates"].includes(pattern)) {
      return `<div class="fr27-skeleton-workspace"><section class="fr27-skeleton-card">${block("58%", "11px")}${[0, 1, 2, 3, 4, 5].map(index => row(index, true)).join("")}</section><section class="fr27-skeleton-card">${block("46%", "11px")}${block("72%", "22px")}<div class="fr27-skeleton-chart">${[34, 61, 48, 78, 55, 90, 66, 82].map(height => block("100%", `${height}%`)).join("")}</div>${block("88%")} ${block("64%")}</section><section class="fr27-skeleton-card">${block("54%", "11px")}${[0, 1, 2, 3, 4].map(index => row(index)).join("")}</section></div>`;
    }
    if (pattern === "events") {
      return `<div class="fr27-skeleton-workspace"><section class="fr27-skeleton-card">${block("54%", "11px")}${block("100%", "62px")}${[0, 1, 2].map(index => row(index)).join("")}</section><section class="fr27-skeleton-card">${block("44%", "11px")}${[0, 1, 2, 3, 4].map(index => row(index)).join("")}</section><section class="fr27-skeleton-card">${block("48%", "11px")}${block("82%", "28px")}${[0, 1, 2, 3].map(index => row(index)).join("")}</section></div>`;
    }
    if (["agenda", "issues", "runoff"].includes(pattern)) {
      return `<div class="fr27-skeleton-workspace"><section class="fr27-skeleton-card">${block("54%", "11px")}${[0, 1, 2, 3, 4, 5].map(index => row(index)).join("")}</section><section class="fr27-skeleton-card">${block("48%", "11px")}<div class="fr27-skeleton-chart">${[48, 72, 36, 86, 61, 74, 53, 92].map(height => block("100%", `${height}%`)).join("")}</div>${[0, 1].map(index => row(index)).join("")}</section><section class="fr27-skeleton-card">${block("42%", "11px")}${[0, 1, 2, 3, 4].map(index => row(index)).join("")}</section></div>`;
    }
    return `<div class="fr27-skeleton-rows">${[0, 1, 2, 3].map(index => row(index)).join("")}</div>`;
  }

  function skeletonElement(pattern, label = "Loading dashboard data") {
    const wrapper = document.createElement("div");
    wrapper.className = `fr27-skeleton-region fr27-skeleton-${pattern}-region`;
    wrapper.setAttribute("role", "status");
    wrapper.setAttribute("aria-label", label);
    wrapper.innerHTML = `<div aria-hidden="true">${skeletonMarkup(pattern)}</div>`;
    return wrapper;
  }

  window.FR27UI = Object.freeze({ skeletonElement, skeletonMarkup, hideTooltip: hide });
})();
