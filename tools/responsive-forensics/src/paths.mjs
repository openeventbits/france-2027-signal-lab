import path from "node:path";
import { fileURLToPath } from "node:url";

export const harnessRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const repoRoot = path.resolve(harnessRoot, "../..");
export const artifactsRoot = path.join(harnessRoot, "artifacts");
export const inventoryJsonPath = path.join(artifactsRoot, "responsive-ownership.json");
export const inventorySummaryPath = path.join(artifactsRoot, "responsive-ownership.md");
export const matrixJsonPath = path.join(artifactsRoot, "viewport-matrix.json");
export const auditJsonPath = path.join(artifactsRoot, "responsive-audit.json");
export const auditSummaryPath = path.join(artifactsRoot, "responsive-audit.md");

export function relativeToRepo(filePath) {
  return path.relative(repoRoot, filePath).replaceAll(path.sep, "/");
}
