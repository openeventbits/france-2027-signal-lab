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

module.exports = { outputPathFromArguments };
