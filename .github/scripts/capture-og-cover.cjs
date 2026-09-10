const fs = require("node:fs");
const { chromium } = require("playwright");

const output = process.env.FR27_OG_OUTPUT;
const url = process.env.FR27_OG_URL;

if (!output || !url) {
  throw new Error("FR27_OG_OUTPUT and FR27_OG_URL are required");
}

const requiredDatasets = [
  "polls",
  "recentChanges",
  "news",
];

(async () => {
  const browser = await chromium.launch({
    headless: true,
  });

  try {
    const page = await browser.newPage({
      viewport: {
        width: 1600,
        height: 840,
      },
      deviceScaleFactor: 0.75,
    });

    await page.addInitScript(() => {
      window.__fr27OgDatasets = {};

      document.addEventListener(
        "hybrid:dataset",
        (event) => {
          const name = event?.detail?.name;
          const status = event?.detail?.status;

          if (name && status) {
            window.__fr27OgDatasets[name] = status;
          }
        }
      );
    });

    await page.goto(url, {
      waitUntil: "domcontentloaded",
      timeout: 45_000,
    });

    await page.waitForFunction(
      (required) => {
        const states =
          window.__fr27OgDatasets || {};

        return required.every(
          (name) => states[name] === "loaded"
        );
      },
      requiredDatasets,
      {
        timeout: 45_000,
      }
    );

    await page.waitForFunction(
      () =>
        document.documentElement
          .dataset.ready === "true",
      null,
      {
        timeout: 45_000,
      }
    );

    await page.addStyleTag({
      content: `
        * {
          animation: none !important;
          transition: none !important;
          caret-color: transparent !important;
        }

        html {
          scrollbar-width: none !important;
        }

        ::-webkit-scrollbar {
          display: none !important;
        }
      `,
    });

    await page.evaluate(async () => {
      await document.fonts.ready;

      window.scrollTo({
        top: 20,
        left: 0,
        behavior: "instant",
      });

      await new Promise(
        (resolve) =>
          requestAnimationFrame(
            () => requestAnimationFrame(resolve)
          )
      );

      const visibleImages =
        [...document.images].filter((img) => {
          const rect =
            img.getBoundingClientRect();

          return (
            rect.bottom > 0
            && rect.top < innerHeight
            && rect.right > 0
            && rect.left < innerWidth
          );
        });

      await Promise.all(
        visibleImages.map((img) => {
          if (img.complete) {
            return Promise.resolve();
          }

          return new Promise((resolve) => {
            const finish = () => resolve();

            img.addEventListener(
              "load",
              finish,
              { once: true }
            );

            img.addEventListener(
              "error",
              finish,
              { once: true }
            );

            setTimeout(finish, 2500);
          });
        })
      );
    });

    await page.waitForTimeout(500);

    await page.screenshot({
      path: output,
      type: "png",
      fullPage: false,
      animations: "disabled",
    });

    const dimensions =
      await page.evaluate(() => ({
        width: innerWidth,
        height: innerHeight,
        scrollY,
      }));

    if (
      dimensions.width !== 1600
      || dimensions.height !== 840
      || Math.abs(dimensions.scrollY - 20) > 1
    ) {
      throw new Error(
        `Unexpected capture geometry: ${
          JSON.stringify(dimensions)
        }`
      );
    }

    console.log(
      `OG cover captured: ${output}`
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
