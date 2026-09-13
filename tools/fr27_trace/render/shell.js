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
    "fieldType",
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

  const traceField = document.querySelector(".trace-field");
  const coverageField = document.querySelector("[data-coverage-field]");
  if (model.fieldType === "coverage_anatomy") {
    const expectedRows = [
      ["share", "COVERAGE SHARE"],
      ["publisher_count", "PUBLISHERS"],
      ["story_cluster_count", "STORY CLUSTERS"],
      ["leading_story_share", "LARGEST STORY"],
      ["leading_publisher_share", "TOP PUBLISHER"],
    ];
    if (!model.field || !Array.isArray(model.field.rows) || model.field.rows.length !== 5) {
      throw new Error("Coverage Anatomy requires exactly five rows");
    }
    for (const field of ["priorLabel", "priorDates", "currentLabel", "currentDates"]) {
      if (typeof model.field[field] !== "string" || model.field[field].length === 0) {
        throw new Error(`Invalid Coverage Anatomy field: ${field}`);
      }
    }
    if (model.field.priorLabel !== "PRIOR" || model.field.currentLabel !== "CURRENT") {
      throw new Error("Coverage Anatomy temporal labels must be PRIOR and CURRENT");
    }

    document.querySelectorAll("[data-coverage]").forEach((element) => {
      element.textContent = model.field[element.dataset.coverage];
    });
    const rows = document.querySelector("[data-coverage-rows]");
    rows.replaceChildren();
    model.field.rows.forEach((row, index) => {
      const [expectedKey, expectedLabel] = expectedRows[index];
      if (
        row.key !== expectedKey
        || row.label !== expectedLabel
        || typeof row.unitLabel !== "string"
        || typeof row.prior !== "string"
        || typeof row.current !== "string"
      ) {
        throw new Error(`Invalid Coverage Anatomy row at index ${index}`);
      }

      const element = document.createElement("div");
      element.className = "coverage-row";
      element.dataset.metric = row.key;

      const label = document.createElement("div");
      label.className = "coverage-row-label";
      const metricLabel = document.createElement("span");
      metricLabel.className = "coverage-metric-label";
      metricLabel.textContent = row.label;
      const unitLabel = document.createElement("span");
      unitLabel.className = "coverage-unit-label";
      unitLabel.textContent = row.unitLabel;
      label.append(metricLabel, unitLabel);

      const prior = document.createElement("div");
      prior.className = "coverage-value coverage-value-prior";
      prior.textContent = row.prior;
      const current = document.createElement("div");
      current.className = "coverage-value coverage-value-current";
      current.textContent = row.current;
      element.append(label, prior, current);
      rows.append(element);
    });

    coverageField.hidden = false;
    traceField.classList.add("coverage-anatomy");
    traceField.setAttribute("aria-label", "Coverage Anatomy prior to current comparison");
  } else if (model.fieldType !== "shell_preview") {
    throw new Error(`Unsupported TRACE field type: ${model.fieldType}`);
  }
  document.documentElement.dataset.traceReady = "true";
};
