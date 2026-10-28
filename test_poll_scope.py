"""Frozen evidence (A), scope semantics (B), and production relationships (C)."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from lxml import html

import poll_scope as scope
import build_poll_explorer as explorer
import build_candidate_signals as signals
from build_poll_hub_static_links import render_historical_archive

ROOT = Path(__file__).resolve().parent
# Independent historical pins: never derive these expectations from the sidecar.
PINS = {
    "fc4749af8f8c351d28d9b067b93b99953c596a45075a2022805f022df731b15c": "9586b3446eea1dcc71d5b821523d091748eab2b1100e398007dbacd2446cbc39",
    "3c0cd997f71cfae9083cef3505aaa2d8ee6b10fa7cc940a9c224b1cf02664310": "7de9820f427b4abb6e580ae53d6db5e09f5db601c04ddae43071e65dfdff5f6f",
    "7620aec7d2dad43cf848da79b84195f0bd5625aa77ce3eb849dd2d8c36ce4780": "118a90111a98d49902657d0b775d501900368dd6fb2af60e9930484a72b53895",
    "0212b6e7cfa97a874ef7d21dd616536693aaa8f43d07c15b736f7b48e97f6cfc": "9f27de3cf7b21b6e12eeb69524a85d161b9731da5998b0ffcf3ab77bfc1be9cc",
    "242142574a93c2d9d30e1de0987aa0970932fed8e0e67144ba4157d2daed5410": "b4619186208f8e1a6cdd42932a22e64ef2029bdead062b17a9f17d57fb80a073",
    "72a2da9cd1969479695b8f09c62f4ea836a77e07a60e07c9fe7dc02eccda5e75": "4dca724e13b14c969423ce9f5ee53654380b0615d92f4b3ea9a209a5ab6f817a",
}
MIXED_ID = "7620aec7d2dad43cf848da79b84195f0bd5625aa77ce3eb849dd2d8c36ce4780"


class PollScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.polls = json.loads((ROOT / "polls.json").read_text(encoding="utf-8"))
        cls.by_id = {e["event_id"]: e for e in cls.polls}
        cls.registry = scope.load_scope_registry()
        cls.payload = explorer.build_poll_explorer(cls.polls)
        cls.packages = signals.build_poll_packages(cls.polls, include_historical=False)

    def test_six_exact_observations_have_independent_frozen_pins(self):
        self.assertEqual(set(self.registry["events"]), set(PINS))
        for identifier, digest in PINS.items():
            self.assertEqual(scope.object_digest(self.by_id[identifier]), digest)
            self.assertEqual(self.registry["events"][identifier]["event_sha256"], digest)
            self.assertFalse(scope.default_2027_eligible(self.by_id[identifier]))
            self.assertEqual(scope.scope_record(self.by_id[identifier])["scope"], scope.RETROSPECTIVE)
        self.assertEqual({e["event_id"] for e in self.polls if not scope.default_2027_eligible(e)}, set(PINS))

    def test_all_other_early_records_remain_unreviewed_and_included(self):
        remaining = [e for e in self.polls if e["fieldwork_start"] < "2024" and e["event_id"] not in PINS]
        self.assertEqual(len(remaining), 23)  # finite 2026-10-28 audit, not a live corpus total
        for event in remaining:
            self.assertEqual(scope.scope_record(event), {"scope": scope.UNREVIEWED})
            self.assertTrue(scope.default_2027_eligible(event))

    def test_dates_macron_lineup_url_and_scenario_key_never_classify_new_ids(self):
        for original in (self.by_id[identifier] for identifier in PINS):
            clone = copy.deepcopy(original)
            clone["event_id"] = "f" * 64
            # Keep the exact original date, Macron, full lineup, URL and scenario key.
            self.assertTrue(scope.default_2027_eligible(clone))
            self.assertEqual(scope.scope_record(clone)["scope"], scope.UNREVIEWED)

    def test_unknown_missing_duplicate_and_changed_observations_fail_closed(self):
        first_id = next(iter(PINS))
        missing = [e for e in self.polls if e["event_id"] != first_id]
        for corpus in (missing, [*self.polls, self.by_id[first_id]]):
            with self.assertRaises(scope.PollScopeError):
                scope.validate_scope_registry(self.registry, corpus)
        unknown = copy.deepcopy(self.registry)
        unknown["events"]["0" * 64] = unknown["events"].pop(first_id)
        with self.assertRaises(scope.PollScopeError):
            scope.validate_scope_registry(unknown, self.polls)
        for key, value in (("source_url", "https://example.org/changed"), ("scenario_key", "x"),
                           ("fieldwork_end", "2022-10-27"), ("pollster", "Other"),
                           ("hypothesis", "changed"), ("round", "second_round")):
            event = copy.deepcopy(self.by_id[first_id])
            event[key] = value
            with self.subTest(key=key), self.assertRaises(scope.PollScopeError):
                scope.scope_record(event)
        event = copy.deepcopy(self.by_id[first_id])
        event["candidates"][0]["score"] += 1
        with self.assertRaises(scope.PollScopeError):
            scope.scope_record(event)

    def test_production_boundary_rejects_partial_corpus_before_writing(self):
        first_id = next(iter(PINS))
        missing = [e for e in self.polls if e["event_id"] != first_id]
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "polls.json"
            output = Path(temporary) / "poll_explorer.json"
            source.write_text(json.dumps(missing), encoding="utf-8")
            output.write_bytes(b"last good publication")
            with self.assertRaises(scope.PollScopeError):
                explorer.build_from_paths(source, output)
            self.assertEqual(output.read_bytes(), b"last good publication")

    def test_registry_schema_and_duplicate_json_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scope.json"
            path.write_text('{"schema_version":"1.0","schema_version":"1.0","events":{}}', encoding="utf-8")
            with self.assertRaises(scope.PollScopeError):
                scope.load_scope_registry(path)
            for key, value in (("scope", "inferred_from_macron"), ("review_date", "2026-02-30"),
                               ("evidence_url", "javascript:alert(1)"), ("evidence_locator", "")):
                registry = copy.deepcopy(self.registry)
                registry["events"][next(iter(PINS))][key] = value
                path.write_text(json.dumps(registry), encoding="utf-8")
                with self.subTest(key=key), self.assertRaises(scope.PollScopeError):
                    scope.load_scope_registry(path)

    def test_projected_evidence_metadata_cannot_mutate_the_registry(self):
        event = self.by_id[next(iter(PINS))]
        record = scope.scope_record(event)
        original = copy.deepcopy(record)
        record["evidence_locator"]["fr"] = "changed by consumer"
        self.assertEqual(scope.scope_record(event), original)

    def test_mixed_wave_has_five_default_scenarios_and_six_archival_scenarios(self):
        wave = next(w for w in self.payload["waves"] if any(s["event_id"] == MIXED_ID for s in w["scenarios"]))
        package = next(p for p in self.packages if p["fieldwork_start"] == "2023-03-30")
        self.assertEqual(len(wave["scenarios"]), 6)
        self.assertEqual(len(package["events"]), 5)
        self.assertEqual({e["event_id"] for e in package["events"]},
                         {s["event_id"] for s in wave["scenarios"]} - {MIXED_ID})
        self.assertEqual(wave["wave_id"], "wave-23ec5fda2b758947")
        self.assertEqual(wave["scenarios"][3]["event_id"], MIXED_ID)  # original #scenario-4

    def test_default_metrics_and_directories_reconcile_with_scenarios(self):
        projected = self.payload["default_2027"]
        eligible_waves = [w for w in self.payload["waves"] if any(s["event_id"] not in PINS for s in w["scenarios"])]
        eligible = [e for e in self.polls if e["event_id"] not in PINS]
        self.assertEqual(projected["metrics"]["scenario_count"], len(self.polls) - 6)
        self.assertEqual(projected["metrics"]["wave_count"], len(self.payload["waves"]) - 5)
        self.assertEqual(projected["metrics"]["period_start"], min(e["fieldwork_start"] for e in eligible))
        self.assertEqual(projected["metrics"]["candidate_count"], len(projected["candidates"]))
        for candidate in projected["candidates"]:
            occurrences = [(w, s) for w in eligible_waves for s in w["scenarios"] if s["event_id"] not in PINS
                           and any(c["candidate_id"] == candidate["candidate_id"] for c in s["candidates"])]
            self.assertEqual(candidate["scenario_count"], len(occurrences))
            self.assertEqual(candidate["wave_count"], len({w["wave_id"] for w, _ in occurrences}))
        for institute in projected["institutes"]:
            expected = [w for w in eligible_waves if w["pollster"] == institute["name"]]
            self.assertEqual(institute["wave_count"], len(expected))
            self.assertEqual(institute["scenario_count"], sum(s["event_id"] not in PINS for w in expected for s in w["scenarios"]))

    def test_candidate_histories_ranges_and_links_use_only_default_observations(self):
        candidates = [{"candidate_id": c["candidate_id"], "candidate_name": c["candidate_name"]} for c in self.payload["candidates"]]
        histories = signals.project_candidate_poll_history(candidates, self.polls)
        self.assertEqual(histories["emmanuel-macron"]["observation_count"], 0)
        self.assertEqual(histories["anne-hidalgo"]["observation_count"], 0)
        self.assertEqual(histories["valerie-pecresse"]["observation_count"], 0)
        for candidate in candidates:
            observations = histories[candidate["candidate_id"]]["observations"]
            expected = []
            for package in self.packages:
                scores = [c["score"] for e in package["events"] for c in e["candidates"] if c["name"] == candidate["candidate_name"]]
                if scores:
                    expected.append((package["package_key"], min(scores), max(scores), len(scores)))
            self.assertCountEqual([(o["package_key"], o["range_min"], o["range_max"], o["hypothesis_count"]) for o in observations], expected)

    def test_bilingual_archive_preserves_scenario_routes_scores_sources_and_anchors(self):
        for language in ("fr", "en"):
            document = html.fromstring(render_historical_archive(language, self.payload["waves"]))
            self.assertEqual(set(document.xpath('.//li/@data-event-id')), set(PINS))
            for item in document.xpath('.//li'):
                identifier = item.attrib["data-event-id"]
                href = item.xpath('.//a/@href')[0]
                self.assertTrue(href.startswith("/en/sondages/" if language == "en" else "/sondages/"))
                path, anchor = href.split("#")
                page = html.fromstring((ROOT / path.strip("/") / "index.html").read_text(encoding="utf-8"))
                scenario = page.get_element_by_id(anchor)
                self.assertIn(identifier, scenario.text_content())
                self.assertIn(self.by_id[identifier]["source_url"], scenario.xpath('.//a/@href'))
                self.assertIn(self.registry["events"][identifier]["evidence_url"], scenario.xpath('.//a/@href'))
                self.assertIn("2022", scenario.xpath('./summary')[0].text_content())
                self.assertEqual(len(scenario.xpath('.//tbody/tr')), len(self.by_id[identifier]["candidates"]))

    def test_repeat_builds_and_json_round_trips_do_not_modify_raw_evidence(self):
        before = copy.deepcopy(self.polls)
        for _ in range(2):
            fetched = json.loads(json.dumps(self.polls))
            scope.validate_scope_registry(self.registry, fetched)
            self.assertEqual(explorer.build_poll_explorer(fetched), self.payload)
        self.assertEqual(self.polls, before)
        self.assertEqual(scope.browser_script(), (ROOT / "assets/poll-scope.js").read_text(encoding="utf-8"))

    def test_fresh_ingestion_replays_keep_scope_without_raw_metadata(self):
        from fetch_polls import integrate_french_migration_source, load_poll_wave_overrides
        source = json.loads(gzip.decompress((ROOT / "test_fixtures/fr27_polling/fr_mediawiki_240570516.json.gz").read_bytes()))
        first = copy.deepcopy(self.polls)
        second = json.loads((ROOT / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
        overrides = load_poll_wave_overrides(ROOT / "poll_wave_overrides.json")
        for _ in range(2):
            first, second, _, _ = integrate_french_migration_source(
                source, first, second, [], overrides, retain_published_history=True)
            self.assertEqual(first, self.polls)
            scope.validate_scope_registry(self.registry, first)
            self.assertEqual({e["event_id"] for e in first if not scope.default_2027_eligible(e)}, set(PINS))
            self.assertTrue(all("election_scope" not in e for e in first))
            self.assertEqual(explorer.build_poll_explorer(first), self.payload)


if __name__ == "__main__":
    unittest.main()
