import { test, expect } from "@playwright/test";
import { startStaticServer } from "../src/server.mjs";
import { waitForDashboard } from "../src/forensics.mjs";

let server;

test.beforeAll(async () => { server = await startStaticServer(); });
test.afterAll(async () => { await server.close(); });

async function expectLocale(page, locale) {
  await expect(page.locator("html")).toHaveAttribute("lang", locale);
  await expect.poll(() => page.evaluate(() => globalThis.FR27I18N?.locale)).toBe(locale);
  await expect(page.locator(`[data-fr27-language='${locale}']`)).toHaveAttribute("aria-current", "page");
  const alternate = locale === "fr" ? "en" : "fr";
  await expect(page.locator(`[data-fr27-language='${alternate}']`)).not.toHaveAttribute("aria-current", "page");
}

test("language switch survives Tier 3 settling and preserves real workspace hash state", async ({ page }) => {
  await page.goto(new URL("/#signal-events", server.url).toString());
  await waitForDashboard(page);
  await expectLocale(page, "fr");
  await expect(page).toHaveURL(url => url.pathname === "/" && url.searchParams.get("lang") === null && url.hash === "#signal-events");

  await page.locator("[data-fr27-language='en']").click();
  await waitForDashboard(page);
  await expect(page).toHaveURL(url => url.pathname === "/en/" && url.searchParams.get("lang") === null && url.hash === "#signal-events");
  await expectLocale(page, "en");

  await page.setViewportSize({ width: 900, height: 800 });
  await expect(page.locator("html")).toHaveClass(/fr27-tier3-active/);
  await expect.poll(() => page.evaluate(() => globalThis.FR27I18N?.locale)).toBe("en");
  await expect(page.locator("[data-fr27-language='en']")).toHaveAttribute("aria-current", "page");
  await expect(page).toHaveURL(url => url.pathname === "/en/" && url.searchParams.get("lang") === null && url.hash === "#signal-events");

  await page.locator("[data-fr27-language='fr']").click();
  await waitForDashboard(page);
  await expect(page).toHaveURL(url => url.pathname === "/" && url.searchParams.get("lang") === null && url.hash === "#signal-events");
  await expectLocale(page, "fr");
});
test("legacy English query migrates to canonical route and preserves state", async ({ page }) => {
  await page.goto(
    new URL("/?lang=en&probe=1#signal-events", server.url).toString()
  );
  await waitForDashboard(page);

  await expect(page).toHaveURL(url =>
    url.pathname === "/en/" &&
    url.searchParams.get("lang") === null &&
    url.searchParams.get("probe") === "1" &&
    url.hash === "#signal-events"
  );
  await expectLocale(page, "en");
});
