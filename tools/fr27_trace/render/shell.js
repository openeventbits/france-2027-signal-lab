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
  const braidField = document.querySelector("[data-signal-braid-field]");
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
  } else if (model.fieldType === "signal_braid") {
    if (!model.field || !Array.isArray(model.field.ticks) || model.field.ticks.length !== 5) {
      throw new Error("Signal Braid requires a validated field and five date ticks");
    }
    for (const field of ["componentLabel", "calendarLabel"]) {
      if (typeof model.field[field] !== "string" || model.field[field].length === 0) {
        throw new Error(`Invalid Signal Braid field: ${field}`);
      }
    }
    document.querySelectorAll("[data-braid]").forEach((element) => {
      element.textContent = model.field[element.dataset.braid];
    });

    const dateAxis = document.querySelector("[data-braid-date-axis]");
    dateAxis.replaceChildren();
    model.field.ticks.forEach((tick) => {
      const label = document.createElement("span");
      label.className = "braid-date-tick";
      label.style.left = `${tick.leftPercent}%`;
      label.textContent = tick.label;
      dateAxis.append(label);
    });

    const renderAnnotation = (plot, annotation, laneClass) => {
      if (!annotation) return;
      const bracket = document.createElement("div");
      bracket.className = `braid-annotation ${laneClass}`;
      bracket.style.left = `${annotation.leftPercent}%`;
      bracket.style.width = `${annotation.widthPercent}%`;
      bracket.dataset.start = annotation.start;
      bracket.dataset.end = annotation.end;
      const label = document.createElement("span");
      label.textContent = annotation.label;
      bracket.append(label);
      plot.append(bracket);
    };

    const renderBars = (laneName, lane, selector, valueKey) => {
      for (const field of ["label", "unitLabel", "maximumLabel"]) {
        if (typeof lane[field] !== "string" || lane[field].length === 0) {
          throw new Error(`Invalid ${laneName} lane field: ${field}`);
        }
      }
      document.querySelectorAll(`[data-braid-${laneName}]`).forEach((element) => {
        element.textContent = lane[element.dataset[`braid${laneName[0].toUpperCase()}${laneName.slice(1)}`]];
      });
      const plot = document.querySelector(selector);
      plot.replaceChildren();
      if (lane.availability !== "observed") {
        plot.classList.add("braid-state");
        plot.textContent = lane.stateLabel || lane.availability.toUpperCase();
        return plot;
      }
      if (!Array.isArray(lane.points) || lane.points.length !== 28) {
        throw new Error(`${laneName} lane requires exactly 28 observations`);
      }
      lane.points.forEach((point, index) => {
        if (
          point.index !== index
          || typeof point.date !== "string"
          || typeof point.value !== "number"
          || typeof point.heightPercent !== "number"
          || point.heightPercent < 0
          || point.heightPercent > 100
        ) {
          throw new Error(`Invalid ${laneName} point at index ${index}`);
        }
        const day = document.createElement("div");
        day.className = "braid-bar-day";
        day.dataset.date = point.date;
        day.dataset[valueKey] = String(point.value);
        const bar = document.createElement("i");
        bar.className = "braid-bar";
        bar.style.height = `${point.heightPercent}%`;
        bar.title = `${point.date} · ${point.valueLabel}`;
        day.append(bar);
        plot.append(day);
      });
      return plot;
    };

    const mediaPlot = renderBars(
      "media",
      model.field.media,
      "[data-braid-media-plot]",
      "recordCount",
    );
    renderAnnotation(mediaPlot, model.field.media.annotation, "braid-coverage-annotation");
    const wikipediaPlot = renderBars(
      "wikipedia",
      model.field.wikipedia,
      "[data-braid-wikipedia-plot]",
      "views",
    );
    renderAnnotation(wikipediaPlot, model.field.wikipedia.annotation, "braid-flash-annotation");

    const agenda = model.field.agenda;
    document.querySelectorAll("[data-braid-agenda]").forEach((element) => {
      element.textContent = agenda[element.dataset.braidAgenda];
    });
    if (!Array.isArray(agenda.rows) || agenda.rows.length !== 16) {
      throw new Error("Agenda lane requires two sections and fourteen fixed topic rows");
    }
    const agendaLabels = document.querySelector("[data-braid-agenda-labels]");
    const agendaMatrix = document.querySelector("[data-braid-agenda-matrix]");
    agendaLabels.replaceChildren();
    agendaMatrix.replaceChildren();
    agenda.rows.forEach((row, rowIndex) => {
      const label = document.createElement("span");
      const matrixRow = document.createElement("div");
      if (row.kind === "section") {
        if (!['policy', 'campaign'].includes(row.section) || row.label !== row.section.toUpperCase()) {
          throw new Error(`Invalid Agenda section at row ${rowIndex}`);
        }
        label.className = "agenda-section-label";
        label.textContent = row.label;
        matrixRow.className = "agenda-matrix-section";
        matrixRow.dataset.section = row.section;
      } else if (row.kind === "topic") {
        if (
          !['policy', 'campaign'].includes(row.section)
          || typeof row.id !== "string"
          || typeof row.code !== "string"
          || !Array.isArray(row.marks)
          || row.marks.length !== 28
        ) {
          throw new Error(`Invalid Agenda topic at row ${rowIndex}`);
        }
        label.className = `agenda-topic-label agenda-topic-label-${row.section}`;
        label.dataset.topic = row.id;
        label.textContent = row.code;
        matrixRow.className = `agenda-topic-row agenda-topic-row-${row.section}`;
        matrixRow.dataset.topic = row.id;
        row.marks.forEach((mark, dateIndex) => {
          if (
            mark.index !== dateIndex
            || typeof mark.date !== "string"
            || !['observed', 'not_observed'].includes(mark.availability)
            || typeof mark.active !== "boolean"
            || (mark.availability !== "observed" && mark.active)
          ) {
            throw new Error(`Invalid Agenda mark at row ${rowIndex}, date ${dateIndex}`);
          }
          const cell = document.createElement("div");
          cell.className = "agenda-mark-cell";
          cell.dataset.date = mark.date;
          cell.dataset.index = String(dateIndex);
          cell.dataset.availability = mark.availability;
          if (mark.availability !== "observed") {
            cell.classList.add("agenda-mark-cell-not-observed");
          }
          if (mark.active) {
            const tick = document.createElement("i");
            tick.className = `agenda-incidence agenda-incidence-${row.section}`;
            tick.dataset.topic = row.id;
            tick.dataset.date = mark.date;
            cell.append(tick);
          }
          matrixRow.append(cell);
        });
      } else {
        throw new Error(`Invalid Agenda row kind at row ${rowIndex}`);
      }
      agendaLabels.append(label);
      agendaMatrix.append(matrixRow);
    });

    const polls = model.field.pollTests;
    document.querySelectorAll("[data-braid-polls]").forEach((element) => {
      element.textContent = polls[element.dataset.braidPolls];
    });
    const pollPlot = document.querySelector("[data-braid-poll-plot]");
    pollPlot.replaceChildren();
    if (polls.availability !== "observed") {
      pollPlot.classList.add("braid-state");
      pollPlot.textContent = polls.stateLabel || "NOT OBSERVED";
    } else {
      polls.packages.forEach((pollPackage, index) => {
        const interval = document.createElement("div");
        interval.className = "poll-interval";
        interval.style.left = `${pollPackage.leftPercent}%`;
        interval.style.width = `${pollPackage.widthPercent}%`;
        interval.style.top = `${11 + (index % 3) * 14}px`;
        interval.dataset.fieldworkStart = pollPackage.fieldworkStart;
        interval.dataset.fieldworkEnd = pollPackage.fieldworkEnd;
        if (pollPackage.continuesLeft) interval.classList.add("continues-left");
        const endpoint = document.createElement("i");
        endpoint.className = "poll-endpoint";
        endpoint.title = `${pollPackage.pollster} · ends ${pollPackage.fieldworkEnd}`;
        interval.append(endpoint);
        pollPlot.append(interval);
      });
    }

    braidField.hidden = false;
    traceField.classList.add("signal-braid");
    traceField.setAttribute("aria-label", "Signal Braid four-lane synchronized candidate trace");
  } else if (model.fieldType !== "shell_preview") {
    throw new Error(`Unsupported TRACE field type: ${model.fieldType}`);
  }
  document.documentElement.dataset.traceReady = "true";
};
