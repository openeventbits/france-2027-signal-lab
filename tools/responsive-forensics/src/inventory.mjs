import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { artifactsRoot, inventoryJsonPath, inventorySummaryPath, relativeToRepo, repoRoot } from "./paths.mjs";

const WIDTH_TOKEN = /(-?\d+(?:\.\d+)?)px/gi;

function lineAt(text, index) {
  return text.slice(0, index).split("\n").length;
}

function maskComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, match => match.replace(/[^\r\n]/g, " "));
}

function matchingBrace(text, openIndex) {
  let depth = 0;
  let quote = "";
  let escaped = false;
  for (let index = openIndex; index < text.length; index += 1) {
    const char = text[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      continue;
    }
    if (char === '"' || char === "'") quote = char;
    else if (char === "{") depth += 1;
    else if (char === "}" && --depth === 0) return index;
  }
  return -1;
}

function selectorLocations(css, bodyStart, bodyEnd, sourceLineOffset) {
  const selectors = [];
  let cursor = bodyStart;
  while (cursor < bodyEnd) {
    const open = css.indexOf("{", cursor);
    if (open < 0 || open >= bodyEnd) break;
    const close = matchingBrace(css, open);
    if (close < 0 || close > bodyEnd) break;
    const boundary = Math.max(css.lastIndexOf("}", open - 1), css.lastIndexOf(";", open - 1), bodyStart - 1);
    const raw = css.slice(boundary + 1, open).trim();
    if (raw.startsWith("@")) {
      selectors.push(...selectorLocations(css, open + 1, close, sourceLineOffset));
    } else if (raw && !raw.includes(":" + " ") && !raw.startsWith("--")) {
      for (const selector of raw.split(",").map(value => value.trim()).filter(Boolean)) {
        selectors.push({ selector, line: sourceLineOffset + lineAt(css, boundary + 1) - 1 });
      }
    }
    cursor = close + 1;
  }
  const seen = new Set();
  return selectors.filter(item => {
    const key = `${item.line}:${item.selector}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function parseWidthThresholds(condition) {
  if (!/width/i.test(condition)) return [];
  const results = [];
  const add = (valuePx, comparator, inclusive, feature = "width") => {
    const key = `${valuePx}:${comparator}:${feature}`;
    if (!results.some(item => item.key === key)) {
      results.push({ key, valuePx, comparator, inclusive, feature });
    }
  };

  for (const match of condition.matchAll(/\b(min|max)-(device-)?width\s*:\s*(-?\d+(?:\.\d+)?)px/gi)) {
    add(Number(match[3]), match[1].toLowerCase() === "min" ? ">=" : "<=", true, `${match[2] || ""}width`);
  }
  for (const match of condition.matchAll(/\b(device-)?width\s*(<=|<|>=|>)\s*(-?\d+(?:\.\d+)?)px/gi)) {
    add(Number(match[3]), match[2], match[2].includes("="), `${match[1] || ""}width`);
  }
  for (const match of condition.matchAll(/(-?\d+(?:\.\d+)?)px\s*(<=|<|>=|>)\s*(device-)?width\b/gi)) {
    const inverse = { "<": ">", "<=": ">=", ">": "<", ">=": "<=" }[match[2]];
    add(Number(match[1]), inverse, match[2].includes("="), `${match[3] || ""}width`);
  }
  if (!results.length) {
    for (const match of condition.matchAll(WIDTH_TOKEN)) add(Number(match[1]), "unknown", null);
  }
  return results
    .map(({ key, ...item }) => item)
    .sort((left, right) => left.valuePx - right.valuePx || left.comparator.localeCompare(right.comparator));
}

function parseCssSource({ text, file, sourceLineOffset = 1, source = "stylesheet" }) {
  const css = maskComments(text);
  const rules = [];
  const pattern = /@(media|container)\b/gi;
  for (const match of css.matchAll(pattern)) {
    const open = css.indexOf("{", match.index);
    const semicolon = css.indexOf(";", match.index);
    if (open < 0 || (semicolon >= 0 && semicolon < open)) continue;
    const close = matchingBrace(css, open);
    if (close < 0) continue;
    const rawPrelude = css.slice(match.index + match[0].length, open).trim().replace(/\s+/g, " ");
    let name = null;
    let condition = rawPrelude;
    if (match[1].toLowerCase() === "container") {
      const conditionStart = rawPrelude.indexOf("(");
      if (conditionStart > 0) {
        name = rawPrelude.slice(0, conditionStart).trim() || null;
        condition = rawPrelude.slice(conditionStart).trim();
      }
    }
    rules.push({
      kind: match[1].toLowerCase(),
      source,
      file,
      line: sourceLineOffset + lineAt(css, match.index) - 1,
      name,
      condition,
      thresholds: parseWidthThresholds(condition),
      selectors: selectorLocations(css, open + 1, close, sourceLineOffset)
    });
  }
  return rules;
}

function contextName(text, index) {
  const before = text.slice(Math.max(0, index - 2500), index);
  const candidates = [...before.matchAll(/(?:function\s+([\w$]+)|(?:const|let|var)\s+([\w$]+)\s*=\s*(?:\([^)]*\)|[\w$]+)\s*=>)/g)];
  const last = candidates.at(-1);
  return last ? (last[1] || last[2]) : null;
}

function compactSnippet(text, start, end = start + 180) {
  return text.slice(start, end).replace(/\s+/g, " ").trim().slice(0, 240);
}

function parseJsSource({ text, file, sourceLineOffset = 1, source = "script" }) {
  const owners = [];
  const add = (kind, index, expression, thresholds = []) => owners.push({
    kind, source, file, line: sourceLineOffset + lineAt(text, index) - 1,
    controller: contextName(text, index), expression, thresholds
  });

  for (const match of text.matchAll(/(?:window\.)?matchMedia\s*\(\s*(["'`])([\s\S]*?)\1\s*\)/g)) {
    const condition = match[2].replace(/\s+/g, " ").trim();
    add("matchMedia", match.index, condition, parseWidthThresholds(condition));
  }
  for (const match of text.matchAll(/(?:window\.)?innerWidth\s*(<=|<|>=|>)\s*(\d+(?:\.\d+)?)/g)) {
    add("innerWidth", match.index, match[0], [{ valuePx: Number(match[2]), comparator: match[1], inclusive: match[1].includes("="), feature: "width" }]);
  }
  for (const match of text.matchAll(/document(?:\.documentElement)?\.clientWidth|documentElement\.clientWidth/g)) {
    add("clientWidth", match.index, compactSnippet(text, match.index));
  }
  const patterns = [
    ["resize-listener", /(?:window\.)?addEventListener\s*\(\s*["']resize["']/g],
    ["media-change-listener", /\.addEventListener\s*\(\s*["']change["']/g],
    ["mutation-observer", /new\s+MutationObserver\s*\(/g],
    ["resize-observer", /new\s+ResizeObserver\s*\(/g],
    ["display-visibility", /\.style\.(?:display|visibility)\s*=/g],
    ["dom-relocation", /\.(?:append|appendChild|insertBefore|insertAdjacentElement|replaceChildren)\s*\(/g],
    ["state-restoration", /\b(?:restore|remember|reconcile|activate|deactivate)[\w$]*\s*\(/gi],
    ["controller-lifecycle", /\b(?:apply|remove)(?:Tier[23]|AgendaTier[23]|IssuesTier[23]|EventsTier[23]|CandidateStructure)[\w$]*\s*\(/gi]
  ];
  for (const [kind, pattern] of patterns) {
    for (const match of text.matchAll(pattern)) add(kind, match.index, compactSnippet(text, match.index));
  }
  for (const match of text.matchAll(/classList\.(?:add|remove|toggle)\s*\(\s*["'`]([^"'`]*(?:tier|responsive|mobile|desktop|narrow|wide)[^"'`]*)["'`]/gi)) {
    add("responsive-class", match.index, compactSnippet(text, match.index));
  }
  return owners.filter(owner => {
    if (owner.kind !== "dom-relocation") return true;
    return /tier[23]-layout\.js$/i.test(file) || /(?:responsive|viewport|tier|moveMedia|restoreMedia)/i.test(owner.controller || "") || /matchMedia|innerWidth/.test(text.slice(Math.max(0, text.indexOf(owner.expression) - 500), text.indexOf(owner.expression) + 500));
  });
}

function extractHtmlBlocks(html, tagName) {
  const blocks = [];
  const pattern = new RegExp(`<${tagName}\\b[^>]*>([\\s\\S]*?)<\\/${tagName}>`, "gi");
  let index = 0;
  for (const match of html.matchAll(pattern)) {
    index += 1;
    const contentStart = match.index + match[0].indexOf(match[1]);
    blocks.push({ index, text: match[1], line: lineAt(html, contentStart) });
  }
  return blocks;
}

function walkFiles(directory, extension) {
  const results = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if ([".git", "node_modules", "artifacts", "test-results", "playwright-report"].includes(entry.name)) continue;
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) results.push(...walkFiles(fullPath, extension));
    else if (entry.isFile() && entry.name.endsWith(extension)) results.push(fullPath);
  }
  return results;
}

export function buildInventory() {
  const cssRules = [];
  const jsOwners = [];
  for (const filePath of walkFiles(repoRoot, ".css")) {
    const file = relativeToRepo(filePath);
    cssRules.push(...parseCssSource({ text: fs.readFileSync(filePath, "utf8"), file }));
  }
  for (const filePath of walkFiles(path.join(repoRoot, "assets"), ".js")) {
    const file = relativeToRepo(filePath);
    jsOwners.push(...parseJsSource({ text: fs.readFileSync(filePath, "utf8"), file }));
  }
  const htmlPath = path.join(repoRoot, "index.html");
  const html = fs.readFileSync(htmlPath, "utf8");
  for (const block of extractHtmlBlocks(html, "style")) {
    cssRules.push(...parseCssSource({ text: block.text, file: "index.html", sourceLineOffset: block.line, source: `inline-style[${block.index}]` }));
  }
  for (const block of extractHtmlBlocks(html, "script")) {
    jsOwners.push(...parseJsSource({ text: block.text, file: "index.html", sourceLineOffset: block.line, source: `inline-script[${block.index}]` }));
  }

  const thresholds = [...new Set([
    ...cssRules.flatMap(rule => rule.thresholds.map(item => item.valuePx)),
    ...jsOwners.flatMap(owner => owner.thresholds.map(item => item.valuePx))
  ])].filter(Number.isFinite).sort((a, b) => a - b);

  return {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    repository: repoRoot,
    css: {
      ruleCount: cssRules.length,
      mediaRuleCount: cssRules.filter(rule => rule.kind === "media").length,
      containerRuleCount: cssRules.filter(rule => rule.kind === "container").length,
      rules: cssRules
    },
    javascript: { ownerCount: jsOwners.length, owners: jsOwners },
    thresholds
  };
}

export function inventoryMarkdown(inventory) {
  const cssFiles = new Map();
  for (const rule of inventory.css.rules) cssFiles.set(rule.file, (cssFiles.get(rule.file) || 0) + 1);
  const jsFiles = new Map();
  for (const owner of inventory.javascript.owners) jsFiles.set(owner.file, (jsFiles.get(owner.file) || 0) + 1);
  const lines = [
    "# FR27 responsive ownership inventory",
    "",
    `Generated: ${inventory.generatedAt}`,
    "",
    `- CSS media rules: ${inventory.css.mediaRuleCount}`,
    `- CSS container rules: ${inventory.css.containerRuleCount}`,
    `- JavaScript ownership signals: ${inventory.javascript.ownerCount}`,
    `- Numerical width thresholds: ${inventory.thresholds.length}`,
    "",
    "## Width thresholds (CSS px)",
    "",
    inventory.thresholds.join(", "),
    "",
    "## CSS ownership by source",
    "",
    ...[...cssFiles].sort().map(([file, count]) => `- ${file}: ${count} responsive at-rules`),
    "",
    "## JavaScript ownership signals by source",
    "",
    ...[...jsFiles].sort().map(([file, count]) => `- ${file}: ${count} signals`),
    "",
    "The JSON companion records conditions, boundary semantics, source lines, governed selectors, controller context, and ownership evidence. Entries identify ownership; they do not classify code as defective.",
    ""
  ];
  return lines.join("\n");
}

export function writeInventory(inventory = buildInventory()) {
  fs.mkdirSync(artifactsRoot, { recursive: true });
  fs.writeFileSync(inventoryJsonPath, JSON.stringify(inventory, null, 2) + "\n");
  fs.writeFileSync(inventorySummaryPath, inventoryMarkdown(inventory));
  return inventory;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const inventory = writeInventory();
  console.log(`Wrote ${relativeToRepo(inventoryJsonPath)}`);
  console.log(`Wrote ${relativeToRepo(inventorySummaryPath)}`);
  console.log(`Discovered ${inventory.thresholds.length} width thresholds across ${inventory.css.ruleCount} CSS at-rules and ${inventory.javascript.ownerCount} JavaScript ownership signals.`);
}
