import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { artifactsRoot } from "../src/paths.mjs";
import { startStaticServer } from "../src/server.mjs";
import { waitForDashboard } from "../src/forensics.mjs";

let server;
test.beforeAll(async () => { server = await startStaticServer(); });
test.afterAll(async () => { await server.close(); });

for (const width of [1024, 1023]) {
  test(`capture unapproved masthead evidence at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 700 });
    await page.goto(server.url);
    await waitForDashboard(page);
    const output = path.join(artifactsRoot, "screenshots", "demo", `masthead-${width}x700.png`);
    fs.mkdirSync(path.dirname(output), { recursive: true });
    await page.locator("header.masthead").screenshot({ path: output, animations: "disabled" });
    expect(fs.statSync(output).size).toBeGreaterThan(1000);
  });
}
