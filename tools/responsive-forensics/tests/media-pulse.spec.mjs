import { test, expect } from "@playwright/test";
import { startStaticServer } from "../src/server.mjs";
import { waitForDashboard } from "../src/forensics.mjs";

let server;

test.beforeAll(async () => { server = await startStaticServer(); });
test.afterAll(async () => { await server.close(); });

test("Tier 3 Media Pulse keeps Coverage selected after controllers settle", async ({ page }) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.setViewportSize({ width: 900, height: 800 });
  await page.goto(server.url);
  await waitForDashboard(page);

  const coverage = page.locator("[data-top-media-tab='coverage']");
  const overview = page.locator("[data-top-media-tab='overview']");
  await expect(coverage).toBeVisible();
  await coverage.click();
  await expect(coverage).toHaveAttribute("aria-selected", "true");
  await expect(overview).toHaveAttribute("aria-selected", "false");

  await page.waitForTimeout(250);
  await expect(coverage).toHaveAttribute("aria-selected", "true");
  await expect(coverage).toHaveClass(/is-active/);
  await expect(page.locator("[data-top-media-panel='coverage']")).toBeVisible();
  expect(errors).toEqual([]);
});

test("Media Pulse selection survives a Tier 2 to Tier 3 transition", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 800 });
  await page.goto(server.url);
  await waitForDashboard(page);
  await page.setViewportSize({ width: 900, height: 800 });
  const coverage = page.locator("[data-top-media-tab='coverage']");
  await expect(coverage).toBeVisible();
  await coverage.click();
  await page.waitForTimeout(250);
  await expect(coverage).toHaveAttribute("aria-selected", "true");
});
