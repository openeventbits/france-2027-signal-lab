import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import { auditJsonPath, auditSummaryPath, artifactsRoot, inventoryJsonPath, relativeToRepo } from "./paths.mjs";
import { componentRegistry, selectComponents } from "./registry.mjs";
import { buildMatrix, loadOrBuildInventory, writeMatrix } from "./matrix.mjs";
import { activateComponent, cdpMatchedRules, collectComponent, compareSnapshots, waitForDashboard } from "./forensics.mjs";
import { startStaticServer } from "./server.mjs";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const [rawKey, inline] = token.slice(2).split("=", 2);
    if (inline != null) args[rawKey] = inline;
    else if (argv[index + 1] && !argv[index + 1].startsWith("--")) args[rawKey] = argv[++index];
    else args[rawKey] = true;
  }
  return args;
}

function parseWidths(raw, matrix, localize) {
  if (localize) {
    const [left, right] = String(localize).split(":").map(Number);
    if (!Number.isInteger(left) || !Number.isInteger(right)) throw new Error("--localize requires LOW:HIGH integer widths");
    const low = Math.max(320, Math.min(left, right));
    const high = Math.max(left, right);
    if (high - low > 250) throw new Error("Localization intervals are limited to 250 CSS pixels");
    return Array.from({ length: high - low + 1 }, (_, index) => high - index);
  }
  if (!raw) return matrix.widths;
  const widths = [...new Set(String(raw).split(",").map(Number))];
  if (widths.some(width => !Number.isInteger(width) || width < 320)) throw new Error("--widths must be comma-separated integers >= 320");
  return widths.sort((a, b) => b - a);
}

function selectorTokens(definition) {
  return [definition.selector, ...(definition.probes || [])]
    .flatMap(selector => selector.match(/[.#][A-Za-z0-9_-]+/g) || [])
    .map(token => token.slice(1));
}

function likelyOwners(inventory, definition, previousWidth, currentWidth, changes) {
  const low = Math.min(previousWidth, currentWidth);
  const high = Math.max(previousWidth, currentWidth);
  const tokens = selectorTokens(definition);
  return inventory.css.rules
    .filter(rule => rule.thresholds.some(item => item.valuePx >= low && item.valuePx <= high))
    .map(rule => {
      const governed = rule.selectors.map(item => item.selector).join(" ");
      const score = tokens.filter(token => governed.includes(token)).length;
      return { score, file: rule.file, line: rule.line, kind: rule.kind, condition: rule.condition, selectors: rule.selectors.filter(item => tokens.some(token => item.selector.includes(token))).slice(0, 8) };
    })
    .filter(item => item.score > 0 || changes.some(change => item.selectors.some(selector => selector.selector.includes(change.selector.replace(/^[.#]/, "")))))
    .sort((a, b) => b.score - a.score || a.file.localeCompare(b.file) || a.line - b.line)
    .slice(0, 8)
    .map(({ score, ...item }) => item);
}

function reportMarkdown(report) {
  const lines = [
    "# FR27 responsive forensic audit",
    "",
    `Generated: ${report.generatedAt}`,
    "",
    `Widths: ${report.widths.join(", ")}`,
    "",
    `Components: ${report.components.join(", ")}`,
    "",
    `Hard findings: ${report.hardFindings.length}; transitions marked for review: ${report.transitions.length}.`,
    ""
  ];
  for (const name of report.components) {
    const transitions = report.transitions.filter(item => item.component === name);
    const hard = report.hardFindings.filter(item => item.component === name);
    lines.push(`## ${name}`, "");
    if (!transitions.length && !hard.length) lines.push("No abrupt transition or hard invariant finding in this probe set.", "");
    for (const transition of transitions) {
      lines.push(`### ${transition.previousWidth} → ${transition.currentWidth}: REVIEW`, "");
      for (const change of transition.changes.slice(0, 12)) lines.push(`- ${change.selector} — ${change.property}: ${change.previous} → ${change.current}`);
      if (transition.likelyOwners.length) {
        lines.push("", "Likely source owners (diagnostic candidates, not defect claims):", "");
        for (const owner of transition.likelyOwners.slice(0, 4)) lines.push(`- ${owner.file}:${owner.line} — \`${owner.condition}\``);
      }
      lines.push("");
    }
    for (const finding of hard) lines.push(`- HARD at ${finding.width}×${finding.height}: ${finding.failure.type}`);
    if (hard.length) lines.push("");
  }
  lines.push("## Interpretation", "", "REVIEW means an abrupt structural signature change was measured. It is not an automatic assertion that the product behavior is wrong. Likely owners are source-correlated candidates; inspect the JSON/CDP evidence before assigning causality.", "");
  return lines.join("\n");
}

export async function runAudit(options = {}) {
  const inventory = options.inventory || loadOrBuildInventory();
  const matrix = options.matrix || writeMatrix(buildMatrix(inventory));
  const components = options.components || Object.keys(componentRegistry);
  const widths = options.widths || matrix.widths;
  const height = options.height || matrix.defaultHeight;
  const server = await startStaticServer();
  const browser = await chromium.launch({ headless: !options.headed });
  const context = await browser.newContext({ viewport: { width: widths[0], height }, colorScheme: "dark", reducedMotion: "reduce" });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", error => consoleErrors.push(error.message));

  const stylesheets = new Map();
  let session = null;
  if (options.cdp !== false) {
    session = await context.newCDPSession(page);
    await session.send("DOM.enable");
    await session.send("CSS.enable");
    session.on("CSS.styleSheetAdded", ({ header }) => stylesheets.set(header.styleSheetId, header));
  }

  const samples = [];
  const transitions = [];
  const hardFindings = [];
  const previousByComponent = new Map();
  try {
    await page.goto(server.url, { waitUntil: "domcontentloaded" });
    await waitForDashboard(page);
    for (const width of widths) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(100);
      const errorsAtWidthStart = consoleErrors.length;
      for (const name of components) {
        const definition = componentRegistry[name];
        await activateComponent(page, definition);
        const sample = await collectComponent(page, name, definition, { width, height }, consoleErrors.slice(errorsAtWidthStart));
        samples.push(sample);
        for (const failure of sample.hardFailures) hardFindings.push({ component: name, width, height, failure });

        const previous = previousByComponent.get(name);
        if (previous) {
          const changes = compareSnapshots(previous, sample);
          if (changes.length) {
            const changedProperties = [...new Set(changes.map(item => item.property).filter(property => !property.includes("visibility/") && !property.startsWith("required")))];
            const cdp = session ? await cdpMatchedRules(session, definition.selector, changedProperties, stylesheets) : [];
            transitions.push({
              component: name,
              previousWidth: previous.viewport.width,
              currentWidth: width,
              changes,
              likelyOwners: likelyOwners(inventory, definition, previous.viewport.width, width, changes),
              cdpMatchedRules: cdp,
              reviewRequired: true
            });
          }
        }
        previousByComponent.set(name, sample);

        if (options.screenshots && sample.root.present && sample.root.visible) {
          const directory = path.join(artifactsRoot, "screenshots", name);
          fs.mkdirSync(directory, { recursive: true });
          await page.locator(definition.selector).first().screenshot({ path: path.join(directory, `${name}-${width}x${height}.png`), animations: "disabled" });
        }
      }
      console.log(`Audited ${width}×${height}`);
    }
  } finally {
    await context.close();
    await browser.close();
    await server.close();
  }

  const report = { schemaVersion: 1, generatedAt: new Date().toISOString(), inventory: relativeToRepo(inventoryJsonPath), widths, height, components, samples, transitions, hardFindings };
  fs.mkdirSync(artifactsRoot, { recursive: true });
  fs.writeFileSync(auditJsonPath, JSON.stringify(report, null, 2) + "\n");
  fs.writeFileSync(auditSummaryPath, reportMarkdown(report));
  return report;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = parseArgs(process.argv.slice(2));
  const inventory = loadOrBuildInventory();
  const matrix = writeMatrix(buildMatrix(inventory));
  const components = selectComponents(String(args.component || args.components || ""));
  const widths = parseWidths(args.widths, matrix, args.localize);
  const height = args.height ? Number(args.height) : matrix.defaultHeight;
  if (!Number.isInteger(height) || height < 320) throw new Error("--height must be an integer >= 320");
  const report = await runAudit({ inventory, matrix, components, widths, height, headed: Boolean(args.headed), screenshots: Boolean(args.screenshots), cdp: args.cdp !== "false" });
  console.log(`Wrote ${relativeToRepo(auditJsonPath)}`);
  console.log(`Wrote ${relativeToRepo(auditSummaryPath)}`);
  console.log(`${report.transitions.length} transitions require human review; ${report.hardFindings.length} hard invariant findings were recorded.`);
  if (args["fail-on-hard"] && report.hardFindings.length) process.exitCode = 1;
}
