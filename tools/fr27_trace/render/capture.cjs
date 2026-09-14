"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const WIDTH = 1280;
const HEIGHT = 720;
const renderRoot = __dirname;
const repositoryRoot = path.resolve(renderRoot, "..", "..", "..");
const outputRoot = path.resolve(repositoryRoot, "_trace_output");

function outputPathFromArguments(argv) {
  const outputIndex = argv.indexOf("--output");
  if (outputIndex < 0 || !argv[outputIndex + 1]) {
    throw new Error("--output is required");
  }
  const output = path.resolve(repositoryRoot, argv[outputIndex + 1]);
  const relative = path.relative(outputRoot, output);
  if (!relative || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`Output must resolve beneath ${outputRoot}`);
  }
  if (path.extname(output).toLowerCase() !== ".png") {
    throw new Error("Output must end in .png");
  }
  return output;
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

function assertPngDimensions(output) {
  const header = fs.readFileSync(output).subarray(0, 24);
  if (header.length !== 24 || header.toString("hex", 1, 4) !== "504e47") {
    throw new Error("Capture did not produce a PNG");
  }
  const width = header.readUInt32BE(16);
  const height = header.readUInt32BE(20);
  if (width !== WIDTH || height !== HEIGHT) {
    throw new Error(`Unexpected PNG dimensions: ${width}x${height}`);
  }
}

async function assertSignalBraidGeometry(page, model) {
  if (model.fieldType !== "signal_braid") return;
  const audit = await page.evaluate(() => {
    const tolerance = 0.25;
    const inside = (inner, outer) => (
      inner.left >= outer.left - tolerance
      && inner.right <= outer.right + tolerance
      && inner.top >= outer.top - tolerance
      && inner.bottom <= outer.bottom + tolerance
    );
    const labels = Array.from(document.querySelectorAll(".agenda-topic-label"));
    const labelRects = labels.map((label) => ({
      topic: label.dataset.topic,
      rect: label.getBoundingClientRect(),
      clips: label.scrollWidth > label.clientWidth || label.scrollHeight > label.clientHeight,
    }));
    const labelOverlaps = [];
    for (let index = 1; index < labelRects.length; index += 1) {
      const previous = labelRects[index - 1];
      const current = labelRects[index];
      if (previous.rect.bottom > current.rect.top + tolerance) {
        labelOverlaps.push([previous.topic, current.topic]);
      }
    }

    const matrix = document.querySelector("[data-braid-agenda-matrix]").getBoundingClientRect();
    const marks = Array.from(document.querySelectorAll(".agenda-incidence"));
    const escapedMarks = marks.filter((mark) => {
      const cell = mark.parentElement.getBoundingClientRect();
      const row = mark.closest(".agenda-topic-row").getBoundingClientRect();
      const rect = mark.getBoundingClientRect();
      return !inside(rect, cell) || !inside(rect, row) || !inside(rect, matrix);
    }).map((mark) => [mark.dataset.topic, mark.dataset.date]);

    const simultaneousByDate = new Map();
    marks.forEach((mark) => {
      const positions = simultaneousByDate.get(mark.dataset.date) || [];
      positions.push(mark.closest(".agenda-topic-row").getBoundingClientRect().top);
      simultaneousByDate.set(mark.dataset.date, positions);
    });
    const collapsedSimultaneous = Array.from(simultaneousByDate.entries())
      .filter(([, positions]) => positions.length > 1 && new Set(positions).size !== positions.length)
      .map(([day]) => day);

    const mediaCells = Array.from(document.querySelectorAll("[data-braid-media-plot] .braid-bar-day"));
    const wikiCells = Array.from(document.querySelectorAll("[data-braid-wikipedia-plot] .braid-bar-day"));
    const firstAgendaRow = document.querySelector(".agenda-topic-row");
    const referenceAgendaCells = firstAgendaRow
      ? Array.from(firstAgendaRow.querySelectorAll(".agenda-mark-cell"))
      : [];
    const misalignedDates = [];
    referenceAgendaCells.forEach((cell, index) => {
      const agendaRect = cell.getBoundingClientRect();
      for (const [lane, candidates] of [["media", mediaCells], ["wikipedia", wikiCells]]) {
        if (candidates.length === 0) continue;
        const candidateRect = candidates[index].getBoundingClientRect();
        if (
          cell.dataset.date !== candidates[index].dataset.date
          || Math.abs(agendaRect.left - candidateRect.left) > tolerance
          || Math.abs(agendaRect.right - candidateRect.right) > tolerance
        ) {
          misalignedDates.push([lane, index]);
        }
      }
    });
    const mediaPlot = document.querySelector("[data-braid-media-plot]").getBoundingClientRect();
    const pollPlot = document.querySelector("[data-braid-poll-plot]").getBoundingClientRect();
    const plotAlignment = {
      agendaMediaLeft: Math.abs(matrix.left - mediaPlot.left),
      agendaMediaRight: Math.abs(matrix.right - mediaPlot.right),
      agendaPollLeft: Math.abs(matrix.left - pollPlot.left),
      agendaPollRight: Math.abs(matrix.right - pollPlot.right),
    };
    return {
      labelCount: labels.length,
      labelClips: labelRects.filter((item) => item.clips).map((item) => item.topic),
      labelOverlaps,
      markCount: marks.length,
      escapedMarks,
      collapsedSimultaneous,
      agendaDateCellCount: referenceAgendaCells.length,
      misalignedDates,
      plotAlignment,
    };
  });
  const expectedMarks = model.field.agenda.rows
    .filter((row) => row.kind === "topic")
    .reduce((total, row) => total + row.marks.filter((mark) => mark.active).length, 0);
  const plotDeltas = Object.values(audit.plotAlignment);
  if (
    audit.labelCount !== 14
    || audit.labelClips.length
    || audit.labelOverlaps.length
    || audit.markCount !== expectedMarks
    || audit.escapedMarks.length
    || audit.collapsedSimultaneous.length
    || audit.agendaDateCellCount !== 28
    || audit.misalignedDates.length
    || plotDeltas.some((delta) => delta > 0.25)
  ) {
    throw new Error(`Signal Braid geometry audit failed: ${JSON.stringify(audit)}`);
  }
  console.log(`Signal Braid geometry: ${JSON.stringify(audit)}`);
}

async function main() {
  const output = outputPathFromArguments(process.argv.slice(2));
  const model = JSON.parse(await readStdin());
  const markup = fs.readFileSync(path.join(renderRoot, "shell.html"), "utf8");
  const styles = fs.readFileSync(path.join(renderRoot, "shell.css"), "utf8");
  const renderer = fs.readFileSync(path.join(renderRoot, "shell.js"), "utf8");
  const documentSource = markup.replace(
    "</head>",
    `<style>${styles}</style><script>${renderer}</script></head>`,
  );

  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: WIDTH, height: HEIGHT },
      deviceScaleFactor: 1,
      serviceWorkers: "block",
    });
    await context.route("**/*", (route) => route.abort());
    const page = await context.newPage();
    await page.setContent(documentSource, { waitUntil: "load" });
    await page.evaluate((payload) => window.renderTraceShell(payload), model);
    await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    await assertSignalBraidGeometry(page, model);

    const geometry = await page.evaluate(() => {
      const canvas = document.querySelector(".trace-canvas").getBoundingClientRect();
      return {
        innerWidth,
        innerHeight,
        documentWidth: document.documentElement.scrollWidth,
        documentHeight: document.documentElement.scrollHeight,
        canvasWidth: canvas.width,
        canvasHeight: canvas.height,
        ready: document.documentElement.dataset.traceReady,
      };
    });
    const expected = [WIDTH, HEIGHT, WIDTH, HEIGHT, WIDTH, HEIGHT, "true"];
    const actual = Object.values(geometry);
    if (actual.some((value, index) => value !== expected[index])) {
      throw new Error(`Unexpected capture geometry: ${JSON.stringify(geometry)}`);
    }

    const footerTypography = await page.evaluate(() => ({
      sourceDataScopeLabel: getComputedStyle(
        document.querySelector(".footer-source .footer-label"),
      ).fontSize,
      methodologicalBoundary: getComputedStyle(
        document.querySelector('.footer-method [data-bind="methodologicalBoundary"]'),
      ).fontSize,
      france2027App: getComputedStyle(
        document.querySelector(".brand-url"),
      ).fontSize,
    }));

    await page.screenshot({
      path: output,
      type: "png",
      fullPage: false,
      animations: "disabled",
      caret: "hide",
    });
    assertPngDimensions(output);
    console.log(`TRACE shell captured: ${output} (${WIDTH}x${HEIGHT})`);
    console.log(`Footer typography: ${JSON.stringify(footerTypography)}`);
  } finally {
    await browser.close();
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

module.exports = { assertSignalBraidGeometry, outputPathFromArguments };
