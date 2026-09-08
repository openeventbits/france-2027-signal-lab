import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildInventory, writeInventory } from "./inventory.mjs";
import { artifactsRoot, inventoryJsonPath, matrixJsonPath, relativeToRepo } from "./paths.mjs";

export const anchorWidths = Object.freeze([
  1707, 1440, 1399, 1398, 1280, 1100, 1024, 1023, 900, 768, 600, 430, 390, 360, 320
]);

export function buildMatrix(inventory) {
  const sourceThresholds = inventory.thresholds.filter(value => Number.isInteger(value));
  const widths = [...new Set([
    ...anchorWidths,
    ...sourceThresholds.flatMap(boundary => [boundary - 1, boundary, boundary + 1])
  ])].filter(width => width >= 320).sort((a, b) => b - a);

  const sourcesByBoundary = Object.fromEntries(sourceThresholds.map(boundary => {
    const sources = [
      ...inventory.css.rules.filter(rule => rule.thresholds.some(item => item.valuePx === boundary)).map(rule => ({ kind: rule.kind, file: rule.file, line: rule.line, condition: rule.condition })),
      ...inventory.javascript.owners.filter(owner => owner.thresholds.some(item => item.valuePx === boundary)).map(owner => ({ kind: owner.kind, file: owner.file, line: owner.line, condition: owner.expression }))
    ];
    return [String(boundary), sources];
  }));

  return {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    supportedMinimumWidth: 320,
    defaultHeight: 900,
    sourceThresholds,
    anchorWidths: [...anchorWidths],
    widths,
    probes: widths.map(width => ({ width, height: 900, reason: anchorWidths.includes(width) ? "anchor-or-boundary-neighbor" : "source-boundary-neighbor" })),
    shortHeightProbes: [
      { width: 1023, height: 600 },
      { width: 760, height: 600 },
      { width: 430, height: 568 }
    ],
    sourcesByBoundary
  };
}

export function loadOrBuildInventory() {
  if (fs.existsSync(inventoryJsonPath)) return JSON.parse(fs.readFileSync(inventoryJsonPath, "utf8"));
  return writeInventory(buildInventory());
}

export function writeMatrix(matrix = buildMatrix(loadOrBuildInventory())) {
  fs.mkdirSync(artifactsRoot, { recursive: true });
  fs.writeFileSync(matrixJsonPath, JSON.stringify(matrix, null, 2) + "\n");
  return matrix;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const matrix = writeMatrix();
  console.log(`Wrote ${relativeToRepo(matrixJsonPath)}`);
  console.log(`${matrix.widths.length} deduplicated probes at or above ${matrix.supportedMinimumWidth}px, plus ${matrix.shortHeightProbes.length} short-height configurations.`);
  console.log(matrix.widths.join(", "));
}
