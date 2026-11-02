import { test, expect } from '@playwright/test';
import { startStaticServer } from '../src/server.mjs';

let server;
test.beforeAll(async () => { server = await startStaticServer(); });
test.afterAll(async () => { await server.close(); });

for (const language of ['fr', 'en']) {
  for (const width of [1707, 1100, 768, 390]) {
    test(`${language} ${width}: visible evidence context and complete periods`, async ({ page }, info) => {
      test.setTimeout(120_000);
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.setViewportSize({ width, height: 932 });
      await page.goto(new URL((language === 'en' ? 'en/index.html' : '') + '#signal-runoff', server.url).href);
      await expect(page.locator('#top-media-pulse-content')).toHaveAttribute('data-refresh-state', 'ready');
      await expect(page.locator('#top-media-pulse-status')).toHaveText('');
      await expect(page.locator('#signal-runoff-panel .runoff-window-context')).toBeVisible();
      const media = page.locator('#top-media-pulse-content');
      await expect(media.locator('.media-bases-toggle')).toContainText('UTC');
      await media.locator('.media-bases-toggle').click();
      await expect(media.locator('.media-bases-content')).toBeVisible();
      await expect(media.locator('.media-bases-content td').first()).toContainText(/\d+\/\d+/);
      await media.locator('.media-bases-content').screenshot({ path: info.outputPath('bases.png') });
      const lastBase = media.locator('.media-bases-content tbody tr').last();
      await expect(lastBase).toBeInViewport();
      await media.locator('.media-bases-content').screenshot({ path: info.outputPath('bases-last.png') });
      await page.keyboard.press('Escape');
      await expect(media.locator('.media-bases-content')).not.toBeVisible();
      await expect(media.locator('.media-topic-unit')).toContainText(language === 'fr' ? 'JOURS' : 'SOURCE-DAYS');
      await expect(media.locator('.top-media-period-legend')).not.toContainText(language === 'fr' ? '2 nov' : '2 NOV');
      await page.screenshot({ path: info.outputPath('dashboard.png'), fullPage: true });

      // Test the visible workspace comparison, including all responsive modes.
      const context = page.locator('#signal-runoff-panel .runoff-window-context');
      await expect(context).toBeVisible();
      await expect(context).toContainText('2026');
      await expect(context).toContainText(language === 'fr' ? 'pas le dernier sondage' : 'not the latest runoff poll');
      const box = await context.boundingBox();
      expect(box.width).toBeGreaterThan(150);
      expect(box.height).toBeGreaterThan(10);
      const fits = await context.evaluate(element => element.scrollWidth <= element.clientWidth + 1);
      expect(fits).toBe(true);
      const lastObservation = await page.locator('#signal-runoff-panel .hybrid-runoff-closest .hybrid-runoff-source-observation').last().boundingBox();
      const footer = await page.locator('#signal-runoff-panel .hybrid-runoff-closest-callout').boundingBox();
      expect(lastObservation.y + lastObservation.height).toBeLessThanOrEqual(footer.y + 1);
      await page.locator('#signal-runoff-panel').screenshot({ path: info.outputPath('runoff.png') });

      const tabs = page.locator('#race-poll-tabs [role="tab"]');
      await expect(tabs).toHaveCount(3);
      for (let tabIndex = 0; tabIndex < await tabs.count(); tabIndex++) {
        if (width !== 1707 && tabIndex > 0) break;
        await tabs.nth(tabIndex).click();
        const select = page.locator('#hypothesis-select');
        const values = await select.locator('option').evaluateAll(options => options.map(option => option.value));
        for (const value of values) {
          if (width !== 1707 && value !== values[0]) break;
          if (await select.isEnabled()) await select.selectOption(value);
          const rows = await page.locator('#bars .bar-row').evaluateAll(elements => elements.map(row => {
            const context = row.querySelector('.race-comparison-context');
            const delta = row.querySelector('.race-change');
            return { text: delta.querySelector('strong').textContent, context: context.textContent,
              contextual: delta.classList.contains('is-contextual'),
              height: context.getBoundingClientRect().height, display: getComputedStyle(context).display };
          }));
          expect(rows.length).toBeGreaterThan(0);
          for (const row of rows) {
            expect(row.context).toBeTruthy();
            expect(row.height).toBeGreaterThan(0);
            expect(row.display).not.toBe('none');
            if (row.contextual) {
              expect(row.text).not.toMatch(/[▲▼≈†]/);
              expect(row.context).toContain(language === 'fr' ? 'Brut' : 'Raw');
            }
          }
        }
      }
      await page.locator('.race-glance').screenshot({ path: info.outputPath('race.png') });
      await page.locator('.top-media-pulse').screenshot({ path: info.outputPath('media.png') });
      expect(errors).toEqual([]);
    });
  }
  test(`${language}: dossier excludes verified historical TF1 article`, async ({ page }) => {
    await page.goto(new URL((language === 'en' ? 'en/' : '') + 'candidates/nicolas-dupont-aignan/index.html', server.url).href);
    await expect(page.locator('body')).not.toContainText('Nicolas Dupont-Aignan dévoile son programme');
    await expect(page.locator('body')).toContainText('Nicolas Dupont-Aignan');
  });
}
