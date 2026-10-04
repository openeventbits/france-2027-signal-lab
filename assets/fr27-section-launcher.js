/* Static HTML disclosure navigation with ordinary browser Tab order. */
(() => {
  "use strict";
  const host = document.querySelector("[data-fr27-section-launcher]");
  if (!host) return;
  const trigger = host.querySelector(".fr27-section-launcher-trigger");
  if (!trigger) return;
  const panel = document.getElementById(trigger.getAttribute("aria-controls"));
  if (!panel || !host.contains(panel)) return;

  function close(restoreFocus = false) {
    panel.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus();
  }

  trigger.addEventListener("click", () => {
    if (!panel.hidden) {
      close(true);
      return;
    }
    panel.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    panel.querySelector("a[href]")?.focus();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      event.preventDefault();
      // The existing HUD handles Escape on window. Preserve trigger focus.
      event.stopPropagation();
      close(true);
    }
  });

  document.addEventListener("click", (event) => {
    if (!panel.hidden && !trigger.contains(event.target) && !panel.contains(event.target)) {
      close(panel.contains(document.activeElement));
    }
  });

  document.addEventListener("focusin", (event) => {
    if (!panel.hidden && !trigger.contains(event.target) && !panel.contains(event.target)) close();
  });
})();
