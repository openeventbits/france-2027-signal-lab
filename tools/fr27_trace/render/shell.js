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
  const flashField = document.querySelector("[data-flash-field]");
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
  } else if (model.fieldType === "flash_shift") {
    if (
      !model.field
      || !Array.isArray(model.field.days)
      || model.field.days.length !== 14
      || !Array.isArray(model.field.summary)
      || model.field.summary.length !== 5
    ) {
      throw new Error("Flash/Shift requires fourteen days and five summary values");
    }
    for (const field of [
      "componentLabel",
      "classificationLabel",
      "previousLabel",
      "previousDates",
      "latestLabel",
      "latestDates",
    ]) {
      if (typeof model.field[field] !== "string" || model.field[field].length === 0) {
        throw new Error(`Invalid Flash/Shift field: ${field}`);
      }
    }
    document.querySelectorAll("[data-flash]").forEach((element) => {
      element.textContent = model.field[element.dataset.flash];
    });

    const chart = document.querySelector("[data-flash-chart]");
    chart.replaceChildren();
    model.field.days.forEach((day, index) => {
      const expectedWindow = index < 7 ? "previous" : "latest";
      if (
        day.window !== expectedWindow
        || typeof day.date !== "string"
        || typeof day.dateLabel !== "string"
        || typeof day.views !== "number"
        || typeof day.viewsLabel !== "string"
        || typeof day.heightPercent !== "number"
        || day.heightPercent < 0
        || day.heightPercent > 100
        || typeof day.isPeak !== "boolean"
      ) {
        throw new Error(`Invalid Flash/Shift day at index ${index}`);
      }
      const element = document.createElement("div");
      element.className = `flash-day flash-day-${day.window}`;
      element.dataset.date = day.date;
      element.dataset.views = String(day.views);
      if (day.isPeak) element.classList.add("flash-day-peak");

      const bar = document.createElement("div");
      bar.className = "flash-bar";
      bar.style.height = `${day.heightPercent}%`;
      const value = document.createElement("span");
      value.className = "flash-value";
      value.textContent = day.viewsLabel;
      const dateLabel = document.createElement("span");
      dateLabel.className = "flash-date";
      dateLabel.textContent = day.dateLabel;
      bar.append(value);
      element.append(bar, dateLabel);
      chart.append(element);
    });

    const summary = document.querySelector("[data-flash-summary]");
    summary.replaceChildren();
    model.field.summary.forEach((item) => {
      if (
        typeof item.key !== "string"
        || typeof item.label !== "string"
        || typeof item.value !== "string"
      ) {
        throw new Error("Invalid Flash/Shift summary value");
      }
      const element = document.createElement("div");
      element.className = "flash-summary-item";
      element.dataset.summary = item.key;
      const label = document.createElement("span");
      label.className = "flash-summary-label";
      label.textContent = item.label;
      const value = document.createElement("span");
      value.className = "flash-summary-value";
      value.textContent = item.value;
      element.append(label, value);
      summary.append(element);
    });

    flashField.hidden = false;
    traceField.classList.add("flash-shift");
    traceField.setAttribute("aria-label", "Flash/Shift fourteen-day Wikipedia attention comparison");
  } else if (model.fieldType !== "shell_preview") {
    throw new Error(`Unsupported TRACE field type: ${model.fieldType}`);
  }
  document.documentElement.dataset.traceReady = "true";
};
