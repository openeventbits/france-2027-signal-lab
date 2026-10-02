#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

CAPTURES = {
    "media": {
        "path": "/",
        "selector": "#top-media-overview-panel",
        "ready_selector": "#top-media-overview-panel .top-media-shift-row",
        "css": """
          html, body { background: #03111d !important; }
          /* Isolate the captured panel so fixed/sticky dashboard chrome cannot
             paint over the screenshot. Descendants may override inherited
             visibility even when their ancestors are hidden. */
          body * { visibility: hidden !important; }
          #top-media-overview-panel,
          #top-media-overview-panel * { visibility: visible !important; }

          /* The live Media Pulse normally occupies one hero-grid column on a
             wide desktop. For social capture, widen the actual parent panel
             rather than only its child; otherwise the child remains laid out
             against the original ~600px grid track and the screenshot contains
             a large blank area. */
          .hero-grid > .top-media-pulse,
          .top-media-pulse,
          .top-media-pulse-content,
          .top-media-pulse .top-media-dashboard {
            width: 960px !important;
            max-width: 960px !important;
            min-width: 960px !important;
          }
          .top-media-pulse {
            height: auto !important;
            min-height: 0 !important;
            max-height: none !important;
            overflow: visible !important;
          }
          .top-media-pulse-content,
          .top-media-pulse .top-media-dashboard {
            height: auto !important;
            overflow: visible !important;
          }
          .top-media-pulse .top-media-dashboard {
            grid-template-columns: minmax(0, 1fr) !important;
            grid-template-rows: minmax(0, 1fr) !important;
          }
          .top-media-pulse .top-media-tabs,
          .top-media-pulse .top-media-latest {
            display: none !important;
          }
          #top-media-overview-panel {
            display: grid !important;
            grid-row: 1 !important;
            grid-template-rows: auto auto !important;
            width: 960px !important;
            max-width: 960px !important;
            min-width: 960px !important;
            height: auto !important;
            min-height: 0 !important;
            max-height: none !important;
            overflow: visible !important;
            position: relative !important;
            z-index: 2147483647 !important;
          }
          #top-media-overview-panel > .top-media-panel-link {
            display: none !important;
          }
          #top-media-overview-panel .top-media-shift {
            min-height: 0 !important;
            height: auto !important;
          }
          #top-media-overview-panel .top-media-shift-list {
            display: block !important;
            min-height: 0 !important;
            height: auto !important;
            max-height: none !important;
            grid-template-rows: none !important;
            overflow: visible !important;
          }
          #top-media-overview-panel .top-media-shift-row,
          #top-media-overview-panel .top-media-shift-row:nth-child(-n + 6) {
            display: grid !important;
            min-height: 42px !important;
            grid-template-columns:
              minmax(220px, 1.15fr)
              72px
              minmax(260px, 1.35fr)
              70px
              110px !important;
            gap: 10px !important;
          }
          #top-media-overview-panel .top-media-shift-row:nth-child(n + 7) {
            display: none !important;
          }
          #top-media-overview-panel .top-media-shift-name {
            font-size: 15px !important;
          }
          #top-media-overview-panel .top-media-shift-row > strong,
          #top-media-overview-panel .top-media-shift-row > b,
          #top-media-overview-panel .top-media-shift-prior-value {
            font-size: 14px !important;
          }
          #top-media-overview-panel .top-media-support-grid {
            height: auto !important;
            min-height: 190px !important;
            overflow: visible !important;
          }
          #top-media-overview-panel .top-media-topic-row,
          #top-media-overview-panel .top-media-publisher-row {
            min-height: 34px !important;
          }
          #top-media-overview-panel .top-media-topic-row > span,
          #top-media-overview-panel .top-media-publisher-row > strong,
          #top-media-overview-panel .top-media-topic-row > strong,
          #top-media-overview-panel .top-media-publisher-row > b {
            font-size: 13px !important;
          }
        """,
    },
    "agenda": {
        "path": "/#signal-agenda",
        "selector": "#signal-agenda-panel .hybrid-agenda-v6-evolution-panel",
        "ready_selector": "#signal-agenda-panel .hybrid-agenda-v6-evolution-panel .hybrid-agenda-v6-matrix-row",
        "css": """
          html, body { background: #03111d !important; }
          body * { visibility: hidden !important; }
          #signal-agenda-panel .hybrid-agenda-v6-evolution-panel,
          #signal-agenda-panel .hybrid-agenda-v6-evolution-panel * {
            visibility: visible !important;
          }
          #signal-agenda-panel,
          #signal-agenda-panel .hybrid-agenda-v6-workspace {
            overflow: visible !important;
          }
          #signal-agenda-panel .hybrid-agenda-v6-workspace {
            display: block !important;
            width: 1200px !important;
            max-width: none !important;
          }
          #signal-agenda-panel .hybrid-agenda-v6-evolution-panel {
            width: 1200px !important;
            max-width: none !important;
            position: relative !important;
            z-index: 2147483647 !important;
          }
        """,
    },
    "issues": {
        "path": "/#signal-issues",
        "selector": "#signal-issues-panel .hybrid-agenda-v6-evolution-panel",
        "ready_selector": "#signal-issues-panel .hybrid-agenda-v6-evolution-panel .hybrid-agenda-v6-matrix-row",
        "css": """
          html, body { background: #03111d !important; }
          body * { visibility: hidden !important; }
          #signal-issues-panel .hybrid-agenda-v6-evolution-panel,
          #signal-issues-panel .hybrid-agenda-v6-evolution-panel * {
            visibility: visible !important;
          }
          #signal-issues-panel,
          #signal-issues-panel .hybrid-agenda-v6-workspace {
            overflow: visible !important;
          }
          #signal-issues-panel .hybrid-agenda-v6-workspace {
            display: block !important;
            width: 1200px !important;
            max-width: none !important;
          }
          #signal-issues-panel .hybrid-agenda-v6-evolution-panel {
            width: 1200px !important;
            max-width: none !important;
            position: relative !important;
            z-index: 2147483647 !important;
          }
        """,
    },
}


def _extract_metrics(page, kind: str) -> dict:
    if kind == "media":
        return page.evaluate(
            """
            () => {
              const rows = [...document.querySelectorAll('#top-media-overview-panel .top-media-shift-row')]
                .map(row => ({
                  name: row.getAttribute('data-hybrid-media-candidate') || '',
                  current: row.querySelector(':scope > strong')?.textContent?.trim() || '',
                  previous: row.querySelector('.top-media-shift-prior-value')?.textContent?.trim() || '',
                  delta: row.querySelector(':scope > b')?.textContent?.trim() || ''
                }));
              return {
                kind: 'media',
                comparison_label: document.querySelector('#top-media-overview-panel .top-media-shift-quality')?.textContent?.trim() || '',
                rows
              };
            }
            """
        )
    if kind in {"agenda", "issues"}:
        panel = "#signal-agenda-panel" if kind == "agenda" else "#signal-issues-panel"
        return page.evaluate(
            """
            ({panel, kind}) => ({
              kind,
              rows: [...document.querySelectorAll(`${panel} .hybrid-agenda-v6-evolution-panel .hybrid-agenda-v6-shift-row`)]
                .map(row => ({
                  label: row.querySelector('.hybrid-agenda-v6-shift-label')?.getAttribute('aria-label')
                    || row.querySelector('.hybrid-agenda-v6-shift-label')?.textContent?.trim()
                    || '',
                  count: row.querySelector('.hybrid-agenda-v6-shift-count')?.textContent?.replace(/\\s+/g, ' ').trim() || '',
                  delta: row.querySelector('.hybrid-agenda-v6-shift-delta')?.textContent?.replace(/\\s+/g, ' ').trim() || '',
                  movement: row.getAttribute('data-movement') || ''
                }))
            })
            """,
            {"panel": panel, "kind": kind},
        )
    raise ValueError(f"unsupported kind: {kind}")




def _capture_when_stable(page, selector: str, output: Path, timeout_ms: int) -> None:
    """Screenshot a dynamic panel, tolerating FR27's asynchronous re-render.

    Agenda/Issues are replaced in the DOM while data contracts settle. A
    Locator may therefore resolve to an element that is detached a moment
    later. Re-resolve the selector on every attempt and only fail after the
    overall timeout.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    last_error: Exception | None = None
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        remaining_ms = max(1000, int((deadline - time.monotonic()) * 1000))
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=min(remaining_ms, 15000))
            page.wait_for_timeout(700 if attempt == 1 else 1200)
            locator.screenshot(
                path=str(output),
                animations="disabled",
                timeout=min(remaining_ms, 20000),
            )
            return
        except PlaywrightError as error:
            last_error = error
            page.wait_for_timeout(750)

    raise RuntimeError(
        f"Could not capture stable element {selector!r} within {timeout_ms} ms: {last_error}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture an FR27 panel for X")
    parser.add_argument("--kind", choices=tuple(CAPTURES), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metrics-output", default="")
    parser.add_argument("--base-url", default="https://france2027.app")
    parser.add_argument("--timeout-ms", type=int, default=120000)
    args = parser.parse_args()

    config = CAPTURES[args.kind]
    target_url = args.base_url.rstrip("/") + config["path"]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1707, "height": 932},
            device_scale_factor=1,
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        page.goto(target_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        page.locator(config["ready_selector"]).first.wait_for(
            state="visible",
            timeout=args.timeout_ms,
        )
        page.wait_for_function(
            "() => !document.fonts || document.fonts.status === 'loaded'",
            timeout=args.timeout_ms,
        )
        # The lower analytical workspaces can render an intermediate DOM and
        # replace it once their asynchronous models settle. Give that replacement
        # a moment to finish before applying social-capture geometry.
        if args.kind in {"agenda", "issues"}:
            page.wait_for_timeout(2500)

        page.add_style_tag(content=config["css"])
        page.wait_for_timeout(900)

        _capture_when_stable(
            page,
            config["selector"],
            output,
            args.timeout_ms,
        )

        # Extract metrics after the successful screenshot so the caption is tied
        # to the stable render that was actually captured.
        metrics = _extract_metrics(page, args.kind)
        if args.metrics_output:
            metrics_path = Path(args.metrics_output)
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            metrics_path.write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        browser.close()
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
