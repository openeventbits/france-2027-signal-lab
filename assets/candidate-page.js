(() => {
  "use strict";

  const CANDIDATE_ID = "marine-le-pen";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const candidateLocale = document.documentElement.lang.toLowerCase().startsWith("en")
    ? "en"
    : "fr";
  const candidateLocaleTag = candidateLocale === "en" ? "en-GB" : "fr-FR";
  const candidateText = (fr, en) => candidateLocale === "en" ? en : fr;

  const topicLabels = Object.freeze(candidateLocale === "en" ? {
    economy_public_finances: "Economy and public finances",
    work_purchasing_power_pensions: "Work, purchasing power and pensions",
    immigration_identity_secularism: "Immigration, identity and secularism",
    security_justice: "Security and justice",
    health_education_public_services: "Health, education and public services",
    climate_energy_agriculture: "Climate, energy and agriculture",
    europe_defence_foreign_affairs: "Europe, defence and foreign affairs",
    institutions_democracy_territories: "Institutions, democracy and territories"
  } : {
    economy_public_finances: "Économie et finances publiques",
    work_purchasing_power_pensions: "Travail, pouvoir d’achat et retraites",
    immigration_identity_secularism: "Immigration, identité et laïcité",
    security_justice: "Sécurité et justice",
    health_education_public_services: "Santé, éducation et services publics",
    climate_energy_agriculture: "Climat, énergie et agriculture",
    europe_defence_foreign_affairs: "Europe, défense et affaires étrangères",
    institutions_democracy_territories: "Institutions, démocratie et territoires"
  });
  const seriesColors = ["#35d5ff", "#8774ff", "#52e5a3", "#ffbf4b"];

  const svgElement = (name, attributes = {}) => {
    const element = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) => {
      element.setAttribute(key, String(value));
    });
    return element;
  };

  const appendTitle = (element, text) => {
    const title = svgElement("title");
    title.textContent = text;
    element.append(title);
  };

  const formatDate = value =>
    new Intl.DateTimeFormat(candidateLocaleTag, { day: "numeric", month: "short", year: "numeric" })
      .format(new Date(`${String(value).slice(0, 10)}T12:00:00Z`));

  const formatNumber = value => new Intl.NumberFormat(candidateLocaleTag).format(value);
  const formatScore = value => new Intl.NumberFormat(candidateLocaleTag, { maximumFractionDigits: 1 }).format(value);

  const formatDateRange = (startValue, endValue) => {
    const start = new Date(`${String(startValue).slice(0, 10)}T12:00:00Z`);
    const end = new Date(`${String(endValue).slice(0, 10)}T12:00:00Z`);
    if (startValue === endValue) return formatDate(startValue);
    const sameMonth = start.getUTCFullYear() === end.getUTCFullYear()
      && start.getUTCMonth() === end.getUTCMonth();
    if (sameMonth) {
      return `${start.getUTCDate()}–${formatDate(endValue)}`;
    }
    const shortStart = new Intl.DateTimeFormat(candidateLocaleTag, { day: "numeric", month: "short" }).format(start);
    return `${shortStart}–${formatDate(endValue)}`;
  };

  const formatPublishedRange = point => (
    Number(point.range_min) === Number(point.range_max)
      ? `${formatScore(point.range_min)}%`
      : `${formatScore(point.range_min)}–${formatScore(point.range_max)}%`
  );

  const formatHypotheses = count => (
    candidateLocale === "en"
      ? `${formatNumber(count)} ${Number(count) === 1 ? "hypothesis" : "hypotheses"}`
      : `${formatNumber(count)} hypothèse${Number(count) === 1 ? "" : "s"}`
  );

  const chartFrame = (container, { maxY, yTicks = 4, yFormatter = formatNumber, width = 920, height = 280 }) => {
    const margin = { top: 18, right: 18, bottom: 30, left: 48 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const svg = svgElement("svg", {
      viewBox: `0 0 ${width} ${height}`,
      preserveAspectRatio: "none",
      "aria-hidden": "true",
      focusable: "false"
    });
    for (let index = 0; index <= yTicks; index += 1) {
      const ratio = index / yTicks;
      const y = margin.top + innerHeight * ratio;
      svg.append(svgElement("line", {
        x1: margin.left,
        y1: y,
        x2: width - margin.right,
        y2: y,
        class: "candidate-chart-grid"
      }));
      const label = svgElement("text", {
        x: margin.left - 8,
        y: y + 3,
        "text-anchor": "end",
        class: "candidate-chart-axis"
      });
      label.textContent = yFormatter(maxY * (1 - ratio));
      svg.append(label);
    }
    container.replaceChildren(svg);
    return {
      svg,
      width,
      height,
      margin,
      innerWidth,
      innerHeight,
      x: (index, count) => margin.left + (count <= 1 ? 0 : (index / (count - 1)) * innerWidth),
      y: value => margin.top + innerHeight - (Math.max(0, value) / maxY) * innerHeight
    };
  };

  const addDateLabels = (frame, points) => {
    if (!points.length) return;
    const indices = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
    indices.forEach((index, position) => {
      const label = svgElement("text", {
        x: frame.x(index, points.length),
        y: frame.height - 8,
        "text-anchor": position === 0 ? "start" : position === indices.length - 1 ? "end" : "middle",
        class: "candidate-chart-axis"
      });
      label.textContent = formatDate(points[index].date || points[index].fieldwork_end);
      frame.svg.append(label);
    });
  };

  const pathFor = (points, x, y, valueFor) =>
    points.map((point, index) => `${index ? "L" : "M"}${x(index, points.length).toFixed(2)},${y(valueFor(point)).toFixed(2)}`).join(" ");

  const renderPollHistory = (container, projection) => {
    const points = projection.polling.first_round_history.observations;
    if (!points.length) return;
    const chartLabel = candidateText(
      `${formatNumber(points.length)} observations chronologiques de sondages pour Marine Le Pen. Les points sont des scores exacts de l’hypothèse sélectionnée et les barres des fourchettes publiées. Aucune moyenne ni interpolation.`,
      `${formatNumber(points.length)} chronological poll observations for Marine Le Pen. Points are exact scores for the selected hypothesis and bars are published ranges. No average or interpolation.`
    );
    const frame = chartFrame(container, {
      maxY: 50,
      yTicks: 5,
      yFormatter: value => `${formatScore(value)}%`,
      width: Math.max(320, Math.round(container.clientWidth || 920)),
      height: 230
    });
    frame.svg.removeAttribute("aria-hidden");
    frame.svg.setAttribute("role", "group");
    frame.svg.setAttribute("aria-label", chartLabel);

    const tooltip = document.createElement("div");
    tooltip.id = "candidate-poll-history-tooltip";
    tooltip.className = "candidate-chart-tooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    container.append(tooltip);

    let activeTrigger = null;
    let hideTimer = 0;
    let lastPointerType = "";
    let touchArmedTrigger = null;
    let touchTimer = 0;

    const tooltipLines = point => {
      const selected = point.selected_score === null
        ? null
        : Number(point.selected_score);
      const lines = [
        `${candidateText("Terrain", "Fieldwork")} : ${formatDateRange(point.fieldwork_start, point.fieldwork_end)}`
      ];
      if (selected === null) {
        lines.push(`${candidateText("Fourchette publiée", "Published range")} : ${formatPublishedRange(point)}`);
      } else {
        lines.push(`${candidateText("Score exact de l’hypothèse sélectionnée", "Exact selected-hypothesis score")} : ${formatScore(selected)}%`);
        if (Number(point.range_min) !== Number(point.range_max)) {
          lines.push(`${candidateText("Fourchette du scénario", "Scenario range")} : ${formatPublishedRange(point)}`);
        }
      }
      const evidence = [formatHypotheses(point.hypothesis_count)];
      if (Number.isFinite(Number(point.sample_size))) {
        evidence.push(`${candidateText("échantillon", "sample")} ${formatNumber(point.sample_size)}`);
      }
      lines.push(evidence.join(" · "));
      return lines;
    };

    const positionTooltip = trigger => {
      const chartRect = container.getBoundingClientRect();
      const triggerRect = trigger.getBoundingClientRect();
      const tooltipWidth = tooltip.offsetWidth;
      const tooltipHeight = tooltip.offsetHeight;
      const gap = 9;
      const edge = 8;
      const anchorX = triggerRect.left + triggerRect.width / 2 - chartRect.left;
      const anchorTop = triggerRect.top - chartRect.top;
      const anchorBottom = triggerRect.bottom - chartRect.top;
      const left = Math.max(
        edge,
        Math.min(anchorX - tooltipWidth / 2, chartRect.width - tooltipWidth - edge)
      );
      const above = anchorTop - tooltipHeight - gap;
      const below = anchorBottom + gap;
      const top = above >= edge
        ? above
        : Math.min(below, chartRect.height - tooltipHeight - edge);
      tooltip.style.left = `${Math.round(left)}px`;
      tooltip.style.top = `${Math.round(Math.max(edge, top))}px`;
    };

    const showTooltip = (trigger, point) => {
      window.clearTimeout(hideTimer);
      activeTrigger = trigger;
      const pollster = document.createElement("strong");
      pollster.textContent = point.pollster;
      const details = tooltipLines(point).map(text => {
        const line = document.createElement("span");
        line.textContent = text;
        return line;
      });
      const source = Array.isArray(point.source_urls) && point.source_urls.length
        ? document.createElement("span")
        : null;
      if (source) {
        source.className = "candidate-chart-tooltip-source";
        source.textContent = candidateText("Voir la source ↗", "View source ↗");
      }
      tooltip.replaceChildren(pollster, ...details, ...(source ? [source] : []));
      tooltip.hidden = false;
      tooltip.classList.add("is-visible");
      positionTooltip(trigger);
    };

    const hideTooltip = trigger => {
      if (trigger && activeTrigger !== trigger) return;
      activeTrigger = null;
      tooltip.classList.remove("is-visible");
      tooltip.hidden = true;
    };

    const scheduleHide = trigger => {
      window.clearTimeout(hideTimer);
      hideTimer = window.setTimeout(() => hideTooltip(trigger), 90);
    };

    points.forEach((point, index) => {
      const x = frame.x(index, points.length);
      const minimumY = frame.y(point.range_min);
      const maximumY = frame.y(point.range_max);
      const selected = point.selected_score === null
        ? null
        : Number(point.selected_score);
      const primarySource = Array.isArray(point.source_urls) && point.source_urls.length
        ? point.source_urls[0]
        : null;
      const trigger = svgElement(primarySource ? "a" : "g", {
        class: `candidate-poll-observation${primarySource ? " has-source" : ""}`,
        "data-observation-kind": selected === null ? "range" : "exact",
        tabindex: 0,
        "aria-describedby": tooltip.id
      });
      if (primarySource) {
        trigger.setAttribute("href", primarySource);
        trigger.setAttribute("target", "_blank");
        trigger.setAttribute("rel", "noopener noreferrer");
        trigger.setAttribute("role", "link");
      } else {
        trigger.setAttribute("role", "img");
      }

      const detailText = [point.pollster, ...tooltipLines(point)].join(". ");
      trigger.setAttribute(
        "aria-label",
        `${detailText}.${primarySource ? candidateText(" Activer pour ouvrir la source.", " Activate to open the source.") : ""}`
      );

      const range = svgElement("line", {
        x1: x,
        y1: minimumY,
        x2: x,
        y2: maximumY,
        class: `candidate-chart-range${selected === null ? "" : " candidate-chart-range-context"}`
      });
      const capMinimum = svgElement("line", {
        x1: x - 3,
        y1: minimumY,
        x2: x + 3,
        y2: minimumY,
        class: `candidate-chart-range${selected === null ? "" : " candidate-chart-range-context"}`
      });
      const capMaximum = svgElement("line", {
        x1: x - 3,
        y1: maximumY,
        x2: x + 3,
        y2: maximumY,
        class: `candidate-chart-range${selected === null ? "" : " candidate-chart-range-context"}`
      });
      trigger.append(range, capMinimum, capMaximum);

      if (selected !== null) {
        const marker = svgElement("circle", {
          cx: x,
          cy: frame.y(selected),
          r: 2.7,
          class: "candidate-chart-point"
        });
        trigger.append(marker);
      }

      trigger.append(
        svgElement("line", {
          x1: x,
          y1: minimumY,
          x2: x,
          y2: maximumY,
          class: "candidate-chart-range-hit-target"
        }),
        svgElement("circle", {
          cx: x,
          cy: frame.y(selected === null ? (Number(point.range_min) + Number(point.range_max)) / 2 : selected),
          r: 8,
          class: "candidate-chart-hit-target"
        })
      );

      trigger.addEventListener("pointerenter", event => {
        lastPointerType = event.pointerType;
        showTooltip(trigger, point);
      });
      trigger.addEventListener("pointerleave", () => scheduleHide(trigger));
      trigger.addEventListener("pointerdown", event => {
        lastPointerType = event.pointerType;
        if (event.pointerType === "touch") showTooltip(trigger, point);
      });
      trigger.addEventListener("focus", () => showTooltip(trigger, point));
      trigger.addEventListener("blur", () => scheduleHide(trigger));
      trigger.addEventListener("keydown", event => {
        lastPointerType = "keyboard";
        if (event.key === "Escape") hideTooltip(trigger);
        if (!primarySource && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          showTooltip(trigger, point);
        }
      });
      trigger.addEventListener("click", event => {
        if (!primarySource) {
          event.preventDefault();
          showTooltip(trigger, point);
          return;
        }
        if (lastPointerType === "touch" && touchArmedTrigger !== trigger) {
          event.preventDefault();
          touchArmedTrigger = trigger;
          window.clearTimeout(touchTimer);
          touchTimer = window.setTimeout(() => {
            if (touchArmedTrigger === trigger) touchArmedTrigger = null;
          }, 4000);
          showTooltip(trigger, point);
        } else if (touchArmedTrigger === trigger) {
          touchArmedTrigger = null;
          window.clearTimeout(touchTimer);
        }
      });

      frame.svg.append(trigger);
    });
    addDateLabels(frame, points);

    document.addEventListener("pointerdown", event => {
      if (activeTrigger && !container.contains(event.target)) hideTooltip();
    });
    window.addEventListener("resize", () => {
      if (activeTrigger) positionTooltip(activeTrigger);
    });
  };

  const renderLineChart = (container, points, valueFor, options = {}) => {
    if (!points.length) return;
    const values = points.map(valueFor);
    const rawMax = Math.max(...values, 1);
    const maxY = options.maxY || rawMax * 1.08;
    const frame = chartFrame(container, {
      maxY,
      yFormatter: options.yFormatter || formatNumber,
      height: options.height ?? 280
    });
    const definitions = svgElement("defs");
    const gradient = svgElement("linearGradient", { id: options.gradientId, x1: 0, y1: 0, x2: 0, y2: 1 });
    gradient.append(
      svgElement("stop", { offset: "0%", "stop-color": options.color || "#35d5ff", "stop-opacity": ".25" }),
      svgElement("stop", { offset: "100%", "stop-color": options.color || "#35d5ff", "stop-opacity": "0" })
    );
    definitions.append(gradient);
    frame.svg.prepend(definitions);
    const linePath = pathFor(points, frame.x, frame.y, valueFor);
    const areaPath = `${linePath} L${frame.x(points.length - 1, points.length)},${frame.margin.top + frame.innerHeight} L${frame.x(0, points.length)},${frame.margin.top + frame.innerHeight} Z`;
    frame.svg.append(svgElement("path", { d: areaPath, fill: `url(#${options.gradientId})` }));
    frame.svg.append(svgElement("path", {
      d: linePath,
      class: "candidate-chart-line",
      stroke: options.color || "#35d5ff"
    }));
    points.forEach((point, index) => {
      const marker = svgElement("circle", {
        cx: frame.x(index, points.length),
        cy: frame.y(valueFor(point)),
        r: index === points.length - 1 ? 3.5 : 2,
        class: "candidate-chart-point",
        stroke: options.color || "#35d5ff"
      });
      appendTitle(marker, options.tooltip(point));
      frame.svg.append(marker);
    });
    addDateLabels(frame, points);
  };

  const renderMediaHistory = (container, projection) => {
    const points = projection.media.recent_history;
    if (!points.length) return;
    const shareFor = point => {
      if (point.share === null || point.share === undefined) return null;
      const value = Number(point.share);
      return Number.isFinite(value) ? value : null;
    };
    const availableShares = points.map(shareFor).filter(value => value !== null);
    const maximumPercent = availableShares.length
      ? Math.max(...availableShares) * 100
      : 0;
    const ceilingPercent = Math.min(100, Math.max(10, Math.ceil(maximumPercent / 10) * 10));
    const tickSteps = [10, 20, 25, 30, 50];
    const tickStep = tickSteps.find(step => (
      ceilingPercent % step === 0
      && ceilingPercent / step >= 2
      && ceilingPercent / step <= 5
    )) || 10;
    const frame = chartFrame(container, {
      maxY: ceilingPercent / 100,
      yTicks: Math.max(1, ceilingPercent / tickStep),
      yFormatter: value => `${Math.round(value * 100)}%`,
      width: Math.max(320, Math.round(container.clientWidth || 920)),
      height: 230
    });
    const chartLabel = candidateText(
      `${formatNumber(points.length)} observations quotidiennes de la part de couverture associée à Marine Le Pen sur 29 jours UTC complets. Ce signal ne mesure ni soutien, ni approbation, ni sentiment, ni intention de vote.`,
      `${formatNumber(points.length)} daily observations of Marine Le Pen's coverage share across 29 complete UTC days. This signal does not measure support, approval, sentiment or voting intention.`
    );
    frame.svg.removeAttribute("aria-hidden");
    frame.svg.setAttribute("role", "group");
    frame.svg.setAttribute("aria-label", chartLabel);

    const definitions = svgElement("defs");
    const gradient = svgElement("linearGradient", {
      id: "candidate-media-gradient",
      x1: 0,
      y1: 0,
      x2: 0,
      y2: 1
    });
    gradient.append(
      svgElement("stop", { offset: "0%", "stop-color": "#35d5ff", "stop-opacity": ".22" }),
      svgElement("stop", { offset: "100%", "stop-color": "#35d5ff", "stop-opacity": "0" })
    );
    definitions.append(gradient);
    frame.svg.prepend(definitions);

    const segments = [];
    let segment = [];
    points.forEach((point, index) => {
      const value = shareFor(point);
      if (value === null) {
        if (segment.length) segments.push(segment);
        segment = [];
        return;
      }
      segment.push({ index, value });
    });
    if (segment.length) segments.push(segment);

    segments.forEach(entries => {
      const linePath = entries.map((entry, index) => (
        `${index ? "L" : "M"}${frame.x(entry.index, points.length).toFixed(2)},${frame.y(entry.value).toFixed(2)}`
      )).join(" ");
      const firstX = frame.x(entries[0].index, points.length);
      const lastX = frame.x(entries[entries.length - 1].index, points.length);
      const baseline = frame.margin.top + frame.innerHeight;
      const areaPath = `${linePath} L${lastX.toFixed(2)},${baseline.toFixed(2)} L${firstX.toFixed(2)},${baseline.toFixed(2)} Z`;
      frame.svg.append(svgElement("path", {
        d: areaPath,
        fill: "url(#candidate-media-gradient)",
        class: "candidate-media-area"
      }));
      frame.svg.append(svgElement("path", {
        d: linePath,
        class: "candidate-chart-line",
        stroke: "#35d5ff"
      }));
    });

    const tooltip = document.createElement("div");
    tooltip.id = "candidate-media-history-tooltip";
    tooltip.className = "candidate-chart-tooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    container.append(tooltip);

    let activeTrigger = null;
    let hideTimer = 0;

    const tooltipLines = point => {
      const share = shareFor(point);
      const lines = [share === null
        ? candidateText("Observation indisponible", "Observation unavailable")
        : `${candidateText("Part quotidienne", "Daily share")} : ${formatScore(share * 100)}%`];
      if (Number.isFinite(Number(point.record_count))) {
        lines.push(`${candidateText("Articles associés", "Associated articles")} : ${formatNumber(point.record_count)}`);
      }
      if (Number.isFinite(Number(point.publisher_count))) {
        lines.push(`${candidateText("Éditeurs", "Publishers")} : ${formatNumber(point.publisher_count)}`);
      }
      return lines;
    };

    const positionTooltip = trigger => {
      const chartRect = container.getBoundingClientRect();
      const triggerRect = trigger.getBoundingClientRect();
      const tooltipWidth = tooltip.offsetWidth;
      const tooltipHeight = tooltip.offsetHeight;
      const gap = 9;
      const edge = 8;
      const anchorX = triggerRect.left + triggerRect.width / 2 - chartRect.left;
      const anchorTop = triggerRect.top - chartRect.top;
      const anchorBottom = triggerRect.bottom - chartRect.top;
      const left = Math.max(
        edge,
        Math.min(anchorX - tooltipWidth / 2, chartRect.width - tooltipWidth - edge)
      );
      const above = anchorTop - tooltipHeight - gap;
      const below = anchorBottom + gap;
      const top = above >= edge
        ? above
        : Math.min(below, chartRect.height - tooltipHeight - edge);
      tooltip.style.left = `${Math.round(left)}px`;
      tooltip.style.top = `${Math.round(Math.max(edge, top))}px`;
    };

    const showTooltip = (trigger, point) => {
      window.clearTimeout(hideTimer);
      activeTrigger = trigger;
      const date = document.createElement("strong");
      date.textContent = formatDate(point.date);
      const details = tooltipLines(point).map(text => {
        const line = document.createElement("span");
        line.textContent = text;
        return line;
      });
      tooltip.replaceChildren(date, ...details);
      tooltip.hidden = false;
      tooltip.classList.add("is-visible");
      positionTooltip(trigger);
    };

    const hideTooltip = trigger => {
      if (trigger && activeTrigger !== trigger) return;
      activeTrigger = null;
      tooltip.classList.remove("is-visible");
      tooltip.hidden = true;
    };

    const scheduleHide = trigger => {
      window.clearTimeout(hideTimer);
      hideTimer = window.setTimeout(() => hideTooltip(trigger), 90);
    };

    points.forEach((point, index) => {
      const share = shareFor(point);
      const available = share !== null;
      const x = frame.x(index, points.length);
      const y = available
        ? frame.y(share)
        : frame.margin.top + frame.innerHeight / 2;
      const trigger = svgElement("g", {
        class: "candidate-media-observation",
        "data-observation-status": available ? "available" : "unavailable",
        tabindex: 0,
        role: "img",
        "aria-describedby": tooltip.id,
        "aria-label": `${formatDate(point.date)}. ${tooltipLines(point).join(". ")}.`
      });
      if (available) {
        trigger.append(svgElement("circle", {
          cx: x,
          cy: y,
          r: index === points.length - 1 ? 3.5 : 2,
          class: "candidate-chart-point",
          stroke: "#35d5ff"
        }));
      }
      trigger.append(svgElement("circle", {
        cx: x,
        cy: y,
        r: 8,
        class: "candidate-chart-hit-target"
      }));
      trigger.addEventListener("pointerenter", () => showTooltip(trigger, point));
      trigger.addEventListener("pointerleave", () => scheduleHide(trigger));
      trigger.addEventListener("pointerdown", event => {
        if (event.pointerType === "touch") showTooltip(trigger, point);
      });
      trigger.addEventListener("focus", () => showTooltip(trigger, point));
      trigger.addEventListener("blur", () => scheduleHide(trigger));
      trigger.addEventListener("keydown", event => {
        if (event.key === "Escape") hideTooltip(trigger);
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          showTooltip(trigger, point);
        }
      });
      trigger.addEventListener("click", event => {
        event.preventDefault();
        showTooltip(trigger, point);
      });
      frame.svg.append(trigger);
    });
    addDateLabels(frame, points);

    document.addEventListener("pointerdown", event => {
      if (activeTrigger && !container.contains(event.target)) hideTooltip();
    });
    window.addEventListener("resize", () => {
      if (activeTrigger) positionTooltip(activeTrigger);
    });
  };

  const renderAttentionHistory = (container, projection) => {
    renderLineChart(
      container,
      projection.attention.daily_series,
      point => point.views,
      {
        height: 140,
        color: "#8774ff",
        gradientId: "candidate-attention-gradient",
        yFormatter: value => formatNumber(Math.round(value)),
        tooltip: point => `${formatDate(point.date)} · ${formatNumber(point.views)} ${candidateText("pages vues", "pageviews")}`
      }
    );
  };

  const renderAgendaHistory = (container, projection) => {
    const points = projection.agenda.evolution;
    const topicIds = projection.agenda.evolution_topic_ids;
    if (!points.length || !topicIds.length) return;
    const rawMax = Math.max(...points.flatMap(point => topicIds.map(id => point.counts[id])), 1);
    const maxY = Math.max(2, Math.ceil(rawMax / 2) * 2);
    const frame = chartFrame(container, {
      maxY,
      yTicks: Math.max(1, maxY / 2),
      yFormatter: value => formatNumber(Math.round(value)),
      width: Math.max(320, Math.round(container.clientWidth || 920)),
      height: 210
    });
    const chartLabel = candidateText(
      `${formatNumber(points.length)} observations quotidiennes des associations thématiques liées à Marine Le Pen. Comptages bruts, sans moyenne, lissage ni interpolation.`,
      `${formatNumber(points.length)} daily observations of topic associations linked to Marine Le Pen. Raw counts, with no average, smoothing or interpolation.`
    );
    frame.svg.removeAttribute("aria-hidden");
    frame.svg.setAttribute("role", "group");
    frame.svg.setAttribute("aria-label", chartLabel);

    const legend = document.createElement("div");
    legend.className = "candidate-agenda-legend";


    topicIds.forEach((topicId, seriesIndex) => {
      const item = document.createElement("span");
      item.style.setProperty("--legend-color", seriesColors[seriesIndex]);
      item.textContent = topicLabels[topicId] || topicId;
      legend.append(item);
      const path = svgElement("path", {
        d: pathFor(points, frame.x, frame.y, point => point.counts[topicId]),
        fill: "none",
        stroke: seriesColors[seriesIndex],
        "stroke-width": 2,
        "vector-effect": "non-scaling-stroke"
      });
      appendTitle(path, topicLabels[topicId] || topicId);
      frame.svg.append(path);
    });

    const zeroBaseline = svgElement("line", {
      class: "candidate-agenda-zero-baseline",
      x1: frame.x(0, points.length),
      x2: frame.x(points.length - 1, points.length),
      y1: frame.y(0),
      y2: frame.y(0),
      stroke: "rgba(82, 122, 145, .72)",
      "stroke-width": 1,
      "vector-effect": "non-scaling-stroke",
      "pointer-events": "none"
    });
    frame.svg.append(zeroBaseline);

    container.before(legend);

    const tooltip = document.createElement("div");
    tooltip.id = "candidate-agenda-history-tooltip";
    tooltip.className = "candidate-chart-tooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    container.append(tooltip);

    let activeTrigger = null;
    let hideTimer = 0;

    const tooltipLines = point => topicIds.map((topicId, seriesIndex) => ({
      color: seriesColors[seriesIndex],
      text: `${topicLabels[topicId] || topicId} : ${formatNumber(point.counts[topicId])}`
    }));

    const positionTooltip = trigger => {
      const chartRect = container.getBoundingClientRect();
      const triggerRect = trigger.getBoundingClientRect();
      const tooltipWidth = tooltip.offsetWidth;
      const tooltipHeight = tooltip.offsetHeight;
      const gap = 9;
      const edge = 8;
      const anchorX = triggerRect.left + triggerRect.width / 2 - chartRect.left;
      const anchorTop = triggerRect.top - chartRect.top;
      const anchorBottom = triggerRect.bottom - chartRect.top;
      const left = Math.max(
        edge,
        Math.min(anchorX - tooltipWidth / 2, chartRect.width - tooltipWidth - edge)
      );
      const above = anchorTop - tooltipHeight - gap;
      const below = anchorBottom + gap;
      const top = above >= edge
        ? above
        : Math.min(below, chartRect.height - tooltipHeight - edge);
      tooltip.style.left = `${Math.round(left)}px`;
      tooltip.style.top = `${Math.round(Math.max(edge, top))}px`;
    };

    const showTooltip = (trigger, point) => {
      window.clearTimeout(hideTimer);
      activeTrigger = trigger;
      const date = document.createElement("strong");
      date.textContent = formatDate(point.date);
      const details = tooltipLines(point).map(detail => {
        const line = document.createElement("span");
        line.className = "candidate-agenda-tooltip-row";
        line.style.setProperty("--series-color", detail.color);
        line.textContent = detail.text;
        return line;
      });
      tooltip.replaceChildren(date, ...details);
      tooltip.hidden = false;
      tooltip.classList.add("is-visible");
      positionTooltip(trigger);
    };

    const hideTooltip = trigger => {
      if (trigger && activeTrigger !== trigger) return;
      activeTrigger = null;
      tooltip.classList.remove("is-visible");
      tooltip.hidden = true;
    };

    const scheduleHide = trigger => {
      window.clearTimeout(hideTimer);
      hideTimer = window.setTimeout(() => hideTooltip(trigger), 90);
    };

    const hitWidth = Math.max(6, Math.min(12, frame.innerWidth / points.length));
    points.forEach((point, index) => {
      const x = frame.x(index, points.length);
      const details = tooltipLines(point);
      const trigger = svgElement("g", {
        class: "candidate-agenda-observation",
        tabindex: 0,
        role: "img",
        "aria-describedby": tooltip.id,
        "aria-label": `${formatDate(point.date)}. ${details.map(detail => detail.text).join(". ")}.`
      });
      trigger.append(
        svgElement("line", {
          x1: x,
          y1: frame.margin.top,
          x2: x,
          y2: frame.margin.top + frame.innerHeight,
          class: "candidate-agenda-focus-line"
        }),
        svgElement("line", {
          x1: x,
          y1: frame.margin.top,
          x2: x,
          y2: frame.margin.top + frame.innerHeight,
          class: "candidate-chart-date-hit-target",
          "stroke-width": hitWidth
        })
      );
      topicIds.forEach((topicId, seriesIndex) => {
        trigger.append(svgElement("circle", {
          cx: x,
          cy: frame.y(point.counts[topicId]),
          r: 2.2,
          class: "candidate-agenda-focus-point",
          fill: seriesColors[seriesIndex]
        }));
      });
      trigger.addEventListener("pointerenter", () => showTooltip(trigger, point));
      trigger.addEventListener("pointerleave", () => scheduleHide(trigger));
      trigger.addEventListener("pointerdown", event => {
        if (event.pointerType === "touch") showTooltip(trigger, point);
      });
      trigger.addEventListener("focus", () => showTooltip(trigger, point));
      trigger.addEventListener("blur", () => scheduleHide(trigger));
      trigger.addEventListener("keydown", event => {
        if (event.key === "Escape") hideTooltip(trigger);
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          showTooltip(trigger, point);
        }
      });
      trigger.addEventListener("click", event => {
        event.preventDefault();
        showTooltip(trigger, point);
      });
      frame.svg.append(trigger);
    });
    addDateLabels(frame, points);

    document.addEventListener("pointerdown", event => {
      if (activeTrigger && !container.contains(event.target)) hideTooltip();
    });
    window.addEventListener("resize", () => {
      if (activeTrigger) positionTooltip(activeTrigger);
    });
  };

  const renderCharts = projection => {
    const renderers = {
      "poll-history": renderPollHistory,
      "media-history": renderMediaHistory,
      "agenda-history": renderAgendaHistory,
      "attention-history": renderAttentionHistory
    };
    document.querySelectorAll("[data-chart]").forEach(container => {
      const render = renderers[container.dataset.chart];
      if (render) render(container, projection);
    });
  };

  const initArchives = () => {
    document.querySelectorAll("[data-archive]").forEach(archive => {
      const button = archive.querySelector("[data-archive-toggle]");
      if (!button) return;
      button.addEventListener("click", () => {
        const expanded = button.getAttribute("aria-expanded") === "true";
        archive.querySelectorAll("[data-archive-extra]").forEach(item => {
          item.hidden = expanded;
        });
        button.setAttribute("aria-expanded", String(!expanded));
        button.textContent = expanded ? archive.dataset.collapsedLabel : archive.dataset.expandedLabel;
      });
    });
  };

  const initLocalNavigation = () => {
    const links = [...document.querySelectorAll(".candidate-local-nav a")];
    const targets = links
      .map(link => document.querySelector(link.getAttribute("href")))
      .filter(Boolean);
    if (!("IntersectionObserver" in window) || !targets.length) return;
    const visible = new Map();
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => visible.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0));
      const active = [...visible.entries()].sort((left, right) => right[1] - left[1])[0];
      if (!active || active[1] <= 0) return;
      links.forEach(link => link.classList.toggle("is-active", link.getAttribute("href") === `#${active[0]}`));
    }, { rootMargin: "-52px 0px -65% 0px", threshold: [0, .15, .5, 1] });
    targets.forEach(target => observer.observe(target));
  };

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

  // FR27 APPLICATION HUD CONTROLLER
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
        ? candidateText("Réduire le dock système", "Collapse system dock")
        : candidateText("Développer le dock système", "Expand system dock");
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
    const timeFormatter = new Intl.DateTimeFormat(candidateLocaleTag, {
      timeZone: "Europe/Paris",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23"
    });
    const dateFormatter = new Intl.DateTimeFormat(candidateLocaleTag, {
      timeZone: "Europe/Paris",
      day: "2-digit",
      month: "short",
      year: "numeric"
    });
    const zoneFormatter = new Intl.DateTimeFormat(candidateLocaleTag, {
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
        .toLocaleUpperCase(candidateLocaleTag);
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
          contactCopy.textContent = candidateText("COPIÉE", "COPIED");
          window.setTimeout(() => { contactCopy.textContent = candidateText("COPIER L’ADRESSE", "COPY ADDRESS"); }, 1600);
        } catch (_) {
          contactCopy.textContent = candidateText("ÉCHEC DE LA COPIE", "COPY FAILED");
          window.setTimeout(() => { contactCopy.textContent = candidateText("COPIER L’ADRESSE", "COPY ADDRESS"); }, 1600);
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

  const loadProjection = async () => {
    const metadata = document.getElementById("candidate-reference-metadata");
    if (!metadata) throw new Error("candidate reference metadata is unavailable");
    const settings = JSON.parse(metadata.textContent);
    if (settings.candidate_id !== CANDIDATE_ID) throw new Error("candidate identity mismatch");
    const response = await fetch(settings.data_url, { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error(`candidate projection request failed: ${response.status}`);
    const projection = await response.json();
    if (projection.schema_version !== settings.schema_version || projection.candidate_id !== CANDIDATE_ID) {
      throw new Error("candidate projection contract mismatch");
    }
    return projection;
  };


  const initCandidateLanguageToggle = () => {
    const peer = document.querySelector("[data-candidate-language-peer]");
    if (!peer) return;

    const base = peer.getAttribute("data-candidate-peer-base");
    if (!base) return;

    peer.setAttribute("href", base);
  };

  const init = async () => {
    initCandidateLanguageToggle();
    initArchives();
    initLocalNavigation();
    initClocks();
    initApplicationHud();
    try {
      renderCharts(await loadProjection());
      document.documentElement.dataset.candidateEnhanced = "true";
    } catch (error) {
      console.warn("Candidate-page enhancement unavailable; semantic HTML remains active.", error);
      document.documentElement.dataset.candidateEnhanced = "false";
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

// === EVENTS VIEWPORT CONTRACT START ===
(() => {
  const initCandidateEventsViewport = () => {
    const grid = document.querySelector("#events .candidate-events-grid");
    if (!grid) return;

    const lists = Array.from(
      grid.querySelectorAll(":scope > .candidate-panel > .candidate-event-list")
    );
    if (lists.length !== 2) return;

    const recentList = lists[1];
    const recentItems = Array.from(
      recentList.querySelectorAll(":scope > .candidate-event-item")
    );
    if (recentItems.length < 3) return;

    const desktopQuery = window.matchMedia("(min-width: 760px)");
    let frame = 0;

    const syncGeometry = () => {
      if (frame) cancelAnimationFrame(frame);

      frame = requestAnimationFrame(() => {
        frame = 0;

        const listRect = recentList.getBoundingClientRect();
        const thirdRect = recentItems[2].getBoundingClientRect();
        const paddingBottom =
          Number.parseFloat(getComputedStyle(recentList).paddingBottom) || 0;

        /*
         * scrollTop keeps this measurement stable if a resize occurs after the
         * reader has scrolled the Recent Events list. No nominal row-height
         * multiplication is used: wrapping, padding and borders are rendered.
         */
        const visibleHeight =
          thirdRect.bottom - listRect.top + recentList.scrollTop + paddingBottom;

        if (Number.isFinite(visibleHeight) && visibleHeight > 0) {
          grid.style.setProperty(
            "--candidate-events-visible-height",
            `${visibleHeight}px`
          );
        }
      });
    };

    syncGeometry();

    if (document.fonts?.ready) {
      document.fonts.ready.then(syncGeometry);
    }

    window.addEventListener("resize", syncGeometry, { passive: true });

    if (typeof desktopQuery.addEventListener === "function") {
      desktopQuery.addEventListener("change", syncGeometry);
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      initCandidateEventsViewport,
      { once: true }
    );
  } else {
    initCandidateEventsViewport();
  }
})();
// === EVENTS VIEWPORT CONTRACT END ===

// === FR27 SCRUTINY SCROLL PATCH START ===
(() => {
    function initScrutinyScrollPanels() {
        const section = document.getElementById("scrutiny");
        if (!section) return;

        const panels = Array.from(
            section.querySelectorAll(":scope .candidate-accountability-grid > .candidate-panel")
        );

        if (panels.length < 2) return;

        const findPanel = (fr, en) =>
            panels.find((panel) => {
                const heading = panel.querySelector(
                    "h3, .candidate-panel-title, .candidate-panel-heading"
                );

                const text = (heading ? heading.textContent : "")
                    .replace(/\s+/g, " ")
                    .trim()
                    .toUpperCase();

                return (
                    text.includes(fr.toUpperCase()) ||
                    text.includes(en.toUpperCase())
                );
            });

        const listPanel =
            findPanel("AFFIRMATIONS SOUS EXAMEN", "CLAIMS UNDER SCRUTINY") ||
            panels[0];

        const statusPanel =
            findPanel("STATUT DE CANDIDATURE", "CANDIDACY STATUS") ||
            panels[1];

        if (!listPanel || !statusPanel || listPanel === statusPanel) return;

        listPanel.classList.add("candidate-scrutiny-panel--list");
        statusPanel.classList.add("candidate-scrutiny-panel--status");

        const listBody = listPanel.querySelector(":scope > .candidate-panel-body");
        if (!listBody) return;

        listBody.classList.add("candidate-scrutiny-scroll-body");

        /*
         * Once JavaScript enhancement is active, expose every projected
         * scrutiny record inside the bounded scroll region. The archive
         * button is no longer needed for this panel.
         */
        listBody.querySelectorAll("[data-archive-extra]").forEach((item) => {
            item.hidden = false;
        });

        listBody.querySelectorAll("[data-archive-toggle]").forEach((button) => {
            button.remove();
        });

        const mobileQuery = window.matchMedia("(max-width: 759.98px)");

        const syncHeights = () => {
            listPanel.style.removeProperty("height");
            listPanel.style.removeProperty("max-height");

            if (mobileQuery.matches) return;

            const statusHeight = Math.ceil(
                statusPanel.getBoundingClientRect().height
            );

            if (statusHeight > 0) {
                listPanel.style.height = `${statusHeight}px`;
                listPanel.style.maxHeight = `${statusHeight}px`;
            }
        };

        const scheduleSync = () => {
            window.requestAnimationFrame(syncHeights);
        };

        scheduleSync();

        window.addEventListener("resize", scheduleSync, { passive: true });

        if (typeof mobileQuery.addEventListener === "function") {
            mobileQuery.addEventListener("change", scheduleSync);
        }

        if ("ResizeObserver" in window) {
            const observer = new ResizeObserver(scheduleSync);
            observer.observe(statusPanel);
            listPanel.__fr27ScrutinyResizeObserver = observer;
        }

        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(scheduleSync);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            initScrutinyScrollPanels,
            { once: true }
        );
    } else {
        initScrutinyScrollPanels();
    }
})();
// === FR27 SCRUTINY SCROLL PATCH END ===
