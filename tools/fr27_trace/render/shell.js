"use strict";

window.renderTraceShell = (model) => {
  const required = [
    "family",
    "status",
    "language",
    "displayLabel",
    "finding",
    "sourceScope",
    "methodologicalBoundary",
    "observationWindow",
    "rendererVersion",
  ];
  for (const field of required) {
    if (typeof model[field] !== "string" || model[field].length === 0) {
      throw new Error(`Invalid render payload field: ${field}`);
    }
  }

  document.documentElement.lang = model.language;
  document.querySelectorAll("[data-bind]").forEach((element) => {
    const value = model[element.dataset.bind];
    element.textContent = value == null ? "" : value;
  });
  document.querySelector(".finding-region").classList.toggle(
    "has-qualifier",
    typeof model.qualifier === "string" && model.qualifier.length > 0,
  );
  document.documentElement.dataset.traceReady = "true";
};
