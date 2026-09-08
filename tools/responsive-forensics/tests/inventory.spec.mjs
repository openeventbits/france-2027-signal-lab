import { test, expect } from "@playwright/test";
import { buildInventory, parseWidthThresholds } from "../src/inventory.mjs";
import { buildMatrix } from "../src/matrix.mjs";
import { componentRegistry } from "../src/registry.mjs";

test("parses inclusive and exclusive media range semantics", () => {
  expect(parseWidthThresholds("(1024px <= width < 1399px)")).toEqual([
    { valuePx: 1024, comparator: ">=", inclusive: true, feature: "width" },
    { valuePx: 1399, comparator: "<", inclusive: false, feature: "width" }
  ]);
  expect(parseWidthThresholds("(max-width: 719px)")).toEqual([
    { valuePx: 719, comparator: "<=", inclusive: true, feature: "width" }
  ]);
});

test("inventory exposes known CSS and JavaScript responsive owners", () => {
  const inventory = buildInventory();
  expect(inventory.css.mediaRuleCount).toBeGreaterThan(100);
  expect(inventory.css.containerRuleCount).toBeGreaterThan(0);
  expect(inventory.thresholds).toEqual(expect.arrayContaining([699, 700, 719, 720, 760, 761, 1023, 1024, 1399]));
  expect(inventory.javascript.owners.some(owner => owner.kind === "matchMedia" && owner.file === "assets/tier3-layout.js")).toBe(true);
  expect(inventory.javascript.owners.some(owner => owner.kind === "mutation-observer" && owner.file === "assets/tier2-layout.js")).toBe(true);
});

test("matrix derives B-1/B/B+1 and registry has the requested logical components", () => {
  const inventory = buildInventory();
  const matrix = buildMatrix(inventory);
  expect(matrix.widths).toEqual(expect.arrayContaining([718, 719, 720, 759, 760, 761, 1022, 1023, 1024]));
  expect(Math.min(...matrix.widths)).toBe(320);
  expect(Object.keys(componentRegistry)).toEqual([
    "masthead", "what-changed", "race", "status", "media", "workspace-controls",
    "candidates", "agenda", "issues", "events", "runoff", "footer"
  ]);
});
