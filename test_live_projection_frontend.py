"""Browser contracts. Optional test-only Playwright; no production dependency.

Run with: python -B -m unittest -v test_live_projection_frontend
Requires a local Playwright Chromium installation. News Wire CI runs the pure
projection/promotion tests independently of browser installation.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import unittest

from live_projection_contract import build_agenda_live_projection, build_issue_live_projection
from build_poll_pages import format_date_range

ROOT = Path(__file__).resolve().parent
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "optional browser test runtime is unavailable")
class LiveHubBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = sync_playwright().start()
        if not Path(cls.runtime.chromium.executable_path).exists():
            cls.runtime.stop(); raise unittest.SkipTest("optional Chromium test browser is unavailable")
        cls.browser = cls.runtime.chromium.launch(headless=True)
        cls.news = json.loads((ROOT / "news_wire.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.runtime.stop()

    def exercise(self, family, language, scenario="success", sort="activity"):
        prefix = "agenda" if family == "agenda" else "issue"
        path = ("agenda/index.html" if language == "fr" else "en/agenda/index.html") if family == "agenda" else ("enjeux/index.html" if language == "fr" else "en/issues/index.html")
        payload = (build_agenda_live_projection if family == "agenda" else build_issue_live_projection)(self.news)
        if scenario == "reordered":
            for index, topic in enumerate(reversed(payload["campaign_agenda"]["topics"])):
                topic["position"] = index
        instant = datetime.fromisoformat(payload["source_snapshot"].replace("Z", "+00:00"))
        if scenario in ("stale", "stale_microsecond", "newer", "offset_equal"):
            if scenario == "stale": instant -= timedelta(seconds=1)
            elif scenario == "stale_microsecond": instant -= timedelta(microseconds=1)
            elif scenario == "newer": instant += timedelta(microseconds=1)
            else: instant = instant.astimezone(timezone(timedelta(hours=2)))
            payload["source_snapshot"] = payload["generated_at"] = instant.isoformat()
        if scenario == "live_naive":
            payload["source_snapshot"] = payload["generated_at"] = instant.replace(tzinfo=None).isoformat()
        if scenario == "live_invalid_day":
            payload["source_snapshot"] = payload["generated_at"] = "2026-02-31T12:00:00Z"
        if scenario == "schema": payload["schema_version"] = "unsupported"
        if scenario == "identity": payload["generated_at"] = "2000-01-01T00:00:00Z"
        if scenario == "counts": payload["topics"][0]["item_count"] += 1
        if scenario == "date": payload["period"]["period_end"] = "2026-02-31"
        if scenario == "mapping":
            if family == "agenda": payload["topics"][0]["id"] = "unknown"
            else: payload["campaign_agenda"]["topics"][0]["id"] = "unknown"
        page = self.browser.new_page()
        try:
            errors = []; page.on("pageerror", lambda error: errors.append(str(error)))
            console_errors = []; page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            html = (ROOT / path).read_text(encoding="utf-8")
            html = re.sub(r'<script\b.*?</script>|<link\b[^>]*>', '', html, flags=re.S)
            page.set_content(html)
            grid = page.locator(f'[data-{prefix}-card-grid]')
            static_stamp = grid.get_attribute(f'data-{prefix}-live-snapshot')
            self.assertEqual(static_stamp, self.news["generated_at"])
            self.assertIsNotNone(datetime.fromisoformat(static_stamp.replace("Z", "+00:00")).tzinfo)
            if scenario.startswith("stale"):
                self.assertLess(instant, datetime.fromisoformat(static_stamp.replace("Z", "+00:00")))
            if scenario in ("static_missing", "static_invalid", "static_naive"):
                value = {"static_missing": None, "static_invalid": "2026-02-31T12:00:00Z",
                         "static_naive": static_stamp.replace("Z", "")}[scenario]
                grid.evaluate("(node, value) => value === null ? node.removeAttribute('data-" + prefix + "-live-snapshot') : node.setAttribute('data-" + prefix + "-live-snapshot', value)", value)

            # Deliberately stale visible fallback proves a successful fetch updates it.
            page.locator(f'[data-{prefix}-live="count"]').first.evaluate('(node) => node.textContent = "99999"')
            initial = page.locator('body').inner_html()
            static_period = format_date_range(payload["period"]["period_start"], payload["period"]["period_end"], language)
            links = page.locator(f'[data-{prefix}-card]').evaluate_all('(nodes) => nodes.map(n => n.getAttribute("href")).sort()')
            page.evaluate("""({payload, scenario}) => {
              window.calls = []; window.ready = false;
              window.fetch = (url, options) => {
                calls.push({url, options});
                return new Promise((resolve, reject) => {
                  window.finishFetch = () => scenario === "failure" ? reject(new Error("offline")) :
                    resolve({ok: scenario !== "http", json: () => scenario === "json" ? Promise.reject(new Error("bad JSON")) : Promise.resolve(payload)});
                });
              };
            }""", {"payload": payload, "scenario": scenario})
            page.add_script_tag(content=(ROOT / f'assets/{"agenda" if family == "agenda" else "issues"}.js').read_text(encoding="utf-8"))
            page.locator(f'[data-{prefix}-sort="{sort}"]').click()
            initial = page.locator('body').inner_html()
            page.evaluate('finishFetch()')
            page.wait_for_timeout(50)
            self.assertEqual(errors, [])
            self.assertEqual(console_errors, [])
            calls = page.evaluate('calls')
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["options"], {"cache": "no-store", "credentials": "same-origin"})
            self.assertEqual(calls[0]["url"], "/agenda/live.json" if family == "agenda" else "/enjeux/live.json")
            if scenario in ("success", "reordered", "newer", "offset_equal"):
                self.assertEqual(page.locator(f'[data-{prefix}-live-metric="period"]').inner_text(), static_period)
                self.assertTrue(page.locator('body').inner_html() != initial, "valid fetch must update stale count")
                self.assertEqual(page.locator(f'[data-{prefix}-card]').evaluate_all('(nodes) => nodes.map(n => n.getAttribute("href")).sort()'), links)
                by_id = {t["id"]: t for t in payload["topics"]}
                nodes = page.locator(f'[data-{prefix}-card]').evaluate_all("""(nodes) => nodes.map(n => ({
                  id: n.getAttribute("data-topic-id") || n.getAttribute("data-issue-id"),
                  count: n.querySelector("[data-agenda-live='count'], [data-issue-live='count']").textContent,
                  volume: Number(n.getAttribute("data-sort-volume")), activity: Number(n.getAttribute("data-sort-activity")),
                  bars: n.querySelectorAll("[data-agenda-live-bars] i, [data-issue-live-bars] i").length
                }))""")
                for node in nodes:
                    t = by_id[node["id"]]
                    self.assertEqual(int(node["count"]), t["source_day_count" if family == "agenda" else "item_count"])
                    self.assertEqual(node["volume"], t["item_count"]); self.assertEqual(node["bars"], 30)
                if sort in ("activity", "volume"):
                    self.assertEqual([n[sort] for n in nodes], sorted((n[sort] for n in nodes), reverse=True))
                self.assertEqual(page.locator(f'[data-{prefix}-sort="{sort}"]').get_attribute('aria-pressed'), 'true')
                # Numeric formatting belongs to each page's locale.
                number = page.locator(f'[data-{prefix}-live="share"]').first.inner_text()
                self.assertIn("," if language == "fr" else ".", number)
                if family == "issues":
                    segments = page.locator('[data-issue-live-segment]').evaluate_all("""nodes => nodes.map(n => ({
                      key: n.getAttribute('data-live-position'), visible: n.querySelector('b')?.textContent
                    }))""")
                    for segment in segments:
                        if segment["visible"] is not None: self.assertEqual(segment["visible"], segment["key"])
                page.locator(f'[data-{prefix}-search]').fill('no-such-topic')
                self.assertEqual(page.locator(f'[data-{prefix}-card]:visible').count(), 0)
            else:
                self.assertTrue(page.locator('body').inner_html() == initial, "failure must retain complete DOM")
        finally:
            page.close()

    def test_success_in_both_languages_and_sorting_after_refresh(self):
        for family in ("agenda", "issues"):
            for language in ("fr", "en"):
                for sort in ("activity", "volume", "movement", "az"):
                    with self.subTest(family=family, language=language, sort=sort): self.exercise(family, language, sort=sort)

    def test_issues_companion_keeps_static_legend_keys_when_source_order_changes(self):
        for language in ("fr", "en"):
            self.exercise("issues", language, "reordered")

    def test_failures_preserve_the_complete_static_snapshot(self):
        for family in ("agenda", "issues"):
            for scenario in ("failure", "http", "json", "schema", "identity", "counts", "date", "mapping"):
                for language in ("fr", "en"):
                    with self.subTest(family=family, scenario=scenario, language=language): self.exercise(family, language, scenario)

    def assert_stale_snapshot_preserved(self, family, language):
        for scenario in ("stale", "stale_microsecond"):
            with self.subTest(scenario=scenario): self.exercise(family, language, scenario)

    def test_stale_agenda_fr_preserves_complete_static_snapshot(self):
        self.assert_stale_snapshot_preserved("agenda", "fr")

    def test_stale_agenda_en_preserves_complete_static_snapshot(self):
        self.assert_stale_snapshot_preserved("agenda", "en")

    def test_stale_issues_fr_preserves_complete_static_snapshot(self):
        self.assert_stale_snapshot_preserved("issues", "fr")

    def test_stale_issues_en_preserves_complete_static_snapshot(self):
        self.assert_stale_snapshot_preserved("issues", "en")

    def test_snapshot_timestamps_fail_closed_without_valid_timezones(self):
        for family in ("agenda", "issues"):
            for language in ("fr", "en"):
                for scenario in ("static_missing", "static_invalid", "static_naive", "live_naive", "live_invalid_day"):
                    with self.subTest(family=family, language=language, scenario=scenario): self.exercise(family, language, scenario)

    def test_equal_offset_and_newer_snapshots_can_enhance(self):
        for family in ("agenda", "issues"):
            for language in ("fr", "en"):
                for scenario in ("newer", "offset_equal"):
                    with self.subTest(family=family, language=language, scenario=scenario): self.exercise(family, language, scenario)

    def test_history_and_detail_pages_do_not_fetch(self):
        for path, asset, prefix in (("agenda/historique/index.html", "agenda", "agenda"), ("enjeux/historique/index.html", "issues", "issue")):
            markup = (ROOT / path).read_text(encoding="utf-8")
            self.assertNotIn(f'data-{prefix}-live-url', markup)
            page = self.browser.new_page()
            try:
                page.set_content(re.sub(r'<script\b.*?</script>|<link\b[^>]*>', '', markup, flags=re.S))
                page.evaluate('() => { window.calls=0; window.fetch=() => {calls++; throw new Error("unexpected fetch");}; }')
                page.add_script_tag(content=(ROOT / f'assets/{asset}.js').read_text(encoding="utf-8"))
                self.assertEqual(page.evaluate('calls'), 0)
            finally: page.close()


if __name__ == "__main__": unittest.main()
