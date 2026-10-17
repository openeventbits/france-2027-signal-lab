"""Offline contract, collector, static UI and publication integration tests."""

import copy
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import build_candidate_polymarket as builder
import candidate_polymarket as contract

ROOT = Path(__file__).resolve().parent
OBSERVED = "2026-10-17T01:00:00Z"


class PolymarketTests(unittest.TestCase):
    def setUp(self):
        self.event = json.loads((ROOT / "test_fixtures/polymarket_event.json").read_text(encoding="utf-8"))
        self.mapping = json.loads((ROOT / "polymarket_candidate_markets.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8"))
        self.ids = {r["candidate_id"] for r in registry["candidates"]}

    def build(self):
        return builder.build_candidate_polymarket(self.event, self.mapping, self.ids, OBSERVED)

    def row(self, cid="marine-le-pen"):
        return next(r for r in self.build()["candidates"] if r["candidate_id"] == cid)

    def test_parse_and_explicit_identity(self):
        row = self.row()
        self.assertEqual(row["market_id"], "679018")
        self.assertEqual(row["candidate_id"], "marine-le-pen")
        self.assertEqual(row["outcome_id"], self.mapping["markets"][
            next(i for i, r in enumerate(self.mapping["markets"]) if r["candidate_id"] == "marine-le-pen")
        ]["outcome_id"])
        self.assertEqual(row["implied_probability"], 0.174)  # synthetic fixture value
        self.assertEqual(row["status"], "observed")

    def test_numeric_validation(self):
        for value in [True, False, "garbage", {}, [], "NaN", "Infinity", "", "-0.01", "1.01"]:
            with self.subTest(value=value):
                self.event["markets"][0]["outcomePrices"] = json.dumps([value, "0.826"])
                with self.assertRaises(contract.CandidatePolymarketError):
                    self.build()

    def test_probability_bounds_and_zero_are_valid(self):
        for value in (0, 1, "0", "1"):
            with self.subTest(value=value):
                self.event["markets"][0]["outcomePrices"] = json.dumps([value, "0.826"])
                row = self.row()
                self.assertEqual(row["status"], "observed")
                self.assertEqual(row["implied_probability"], float(value))

    def test_publication_numeric_type(self):
        for value in ("0.174", True, float("nan"), float("inf"), -1, 2):
            payload = self.build()
            next(r for r in payload["candidates"] if r["candidate_id"] == "marine-le-pen")["implied_probability"] = value
            with self.subTest(value=value), self.assertRaises(contract.CandidatePolymarketError):
                contract.validate_candidate_polymarket(payload)

    def test_missing_market_and_no_mapping_are_unavailable(self):
        for cid, state in [("david-lisnard", "unavailable_missing_market"), ("anasse-kazib", "unavailable_no_market")]:
            row = self.row(cid)
            self.assertEqual(row["status"], state)
            self.assertIsNone(row["implied_probability"])

    def test_registry_additions_do_not_require_fabricated_observations(self):
        snapshot = self.build()
        row = contract.candidate_record(snapshot, "new-registry-candidate")
        self.assertEqual(row["status"], "unavailable_no_market")
        self.assertIsNone(row["implied_probability"])
        self.assertIsNone(row["market_id"])
        self.assertNotIn(row, snapshot["candidates"])

    def test_publication_cannot_drop_a_reviewed_mapping(self):
        payload = self.build()
        payload["candidates"] = [r for r in payload["candidates"] if r["candidate_id"] != "marine-le-pen"]
        with self.assertRaises(contract.CandidatePolymarketError):
            contract.validate_candidate_polymarket(payload, mapping=self.mapping)

    def test_null_price_is_not_zero(self):
        for prices in (None, '[null, null]'):
            self.event["markets"][0]["outcomePrices"] = prices
            self.assertEqual(self.row()["status"], "unavailable_price")
            self.assertIsNone(self.row()["implied_probability"])

    def test_unknown_outside_registry_other_and_placeholder_are_inspectable(self):
        ignored = self.build()["ignored_markets"]
        self.assertEqual({r["name"] for r in ignored}, {"Manuel Bompard", "Other", "Person K"})
        self.assertTrue(all(r["reason"] == "unreviewed_market" for r in ignored))

    def test_renamed_label_is_not_guessed(self):
        self.event["markets"][0]["groupItemTitle"] = "Marine"
        with self.assertRaisesRegex(contract.CandidatePolymarketError, "identity or candidate label"):
            self.build()

    def test_wrong_event_or_market_or_outcome(self):
        for key, value in [("slug", "wrong"), ("version", "v2"), ("outcomes", '["Maybe", "No"]'),
                           ("clobTokenIds", '["1", "2"]')]:
            original = copy.deepcopy(self.event)
            with self.subTest(key=key):
                self.event["markets"][0][key] = value
                with self.assertRaises(contract.CandidatePolymarketError):
                    self.build()
            self.event = original
        for key in ("id", "slug"):
            original = self.event[key]
            self.event[key] = "wrong"
            with self.assertRaises(contract.CandidatePolymarketError):
                self.build()
            self.event[key] = original

    def test_empty_response_never_becomes_valid(self):
        for event in (None, [], {}, {**self.event, "markets": []}, {**self.event, "markets": self.event["markets"][2:]}):
            self.event = event
            with self.assertRaises(contract.CandidatePolymarketError):
                self.build()

    def test_malformed_nested_fields(self):
        for key, value in [("outcomes", "oops"), ("outcomePrices", "null"),
                           ("outcomePrices", '["0.1"]'), ("active", None), ("updatedAt", "today")]:
            original = copy.deepcopy(self.event)
            self.event["markets"][0][key] = value
            with self.subTest(key=key), self.assertRaises(contract.CandidatePolymarketError):
                self.build()
            self.event = original

    def test_closed_market_is_unavailable(self):
        self.event["markets"][0]["closed"] = True
        self.assertEqual(self.row()["status"], "unavailable_market_inactive")
        self.assertIsNone(self.row()["implied_probability"])

    def test_duplicate_market_or_mapping_rejected(self):
        self.event["markets"].append(copy.deepcopy(self.event["markets"][0]))
        with self.assertRaises(contract.CandidatePolymarketError):
            self.build()
        self.event["markets"].pop()
        self.mapping["markets"].append(copy.deepcopy(self.mapping["markets"][0]))
        with self.assertRaises(contract.CandidatePolymarketError):
            self.build()

    def test_future_or_naive_timestamp_rejected(self):
        for value in ("2026-10-18T00:00:00Z", "2026-10-17T00:00:00", 42):
            self.event["updatedAt"] = value
            with self.assertRaises(contract.CandidatePolymarketError):
                self.build()

    def test_deterministic_without_normalization(self):
        first = self.build()
        self.event["markets"].reverse()
        self.mapping["markets"].reverse()
        self.assertEqual(json.dumps(first), json.dumps(self.build()))
        self.assertEqual(sum(r["implied_probability"] or 0 for r in first["candidates"]), .348)

    def response(self, body):
        response = io.BytesIO(body)
        response.status = 200
        return response

    def test_fetch_official_endpoint_timeout_and_user_agent(self):
        opener = Mock(return_value=self.response(json.dumps(self.event).encode()))
        self.assertEqual(builder.fetch_event(opener=opener), self.event)
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, contract.API_URL)
        self.assertEqual(opener.call_args.kwargs, {"timeout": 20})
        self.assertIn("FR27", request.get_header("User-agent"))

    def test_network_failure_retries_and_fails(self):
        opener = Mock(side_effect=URLError("offline"))
        sleep = Mock()
        with self.assertRaises(contract.CandidatePolymarketError):
            builder.fetch_event(opener=opener, sleep=sleep)
        self.assertEqual(opener.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_http_failure_and_retry(self):
        for code, attempts in [(404, 1), (429, 3), (503, 3)]:
            opener = Mock(side_effect=HTTPError(contract.API_URL, code, "error", {}, None))
            with self.subTest(code=code), self.assertRaises(contract.CandidatePolymarketError):
                builder.fetch_event(opener=opener, sleep=Mock())
            self.assertEqual(opener.call_count, attempts)

    def test_malformed_json_and_size_limit(self):
        for body in (b"not JSON", b"\xff", b" " * (builder.MAX_BYTES + 1)):
            with self.assertRaises(contract.CandidatePolymarketError):
                builder.fetch_event(opener=Mock(return_value=self.response(body)))

    def test_failure_preserves_previous_bytes(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            output = Path(tmp) / "signal.json"
            output.write_bytes(b"previous valid publication")
            for fetch in (Mock(side_effect=contract.CandidatePolymarketError("offline")), lambda: {}):
                with self.assertRaises(contract.CandidatePolymarketError):
                    builder.collect(output, mapping_path=ROOT / "polymarket_candidate_markets.json",
                                    registry_path=ROOT / "candidate_candidacy_status.json", fetch=fetch)
                self.assertEqual(output.read_bytes(), b"previous valid publication")

    def test_reviewed_mapping_required_for_publication(self):
        payload = self.build()
        row = next(r for r in payload["candidates"] if r["candidate_id"] == "marine-le-pen")
        row["outcome_id"] = "123"
        with self.assertRaises(contract.CandidatePolymarketError):
            contract.validate_candidate_polymarket(payload, mapping=self.mapping, candidate_ids=self.ids)

    def test_localized_static_available_and_unavailable(self):
        import build_candidate_reference as reference
        for lang, label, disclaimer, unavailable in [
            ("fr", "Probabilité implicite", "ni une intention de vote ni une prévision FR27", "Indisponible"),
            ("en", "Implied probability", "not voting intention and not an FR27 forecast", "Unavailable")
        ]:
            row = self.row()
            row.update(observed_at=OBSERVED, stale_after_hours=48)
            rendered = reference.render_polymarket({"polymarket": row}, lang)
            self.assertIn(label, rendered)
            self.assertIn(disclaimer, rendered)
            self.assertIn("17,4\u00a0%" if lang == "fr" else "17.4%", rendered)
            self.assertIn(row["source_url"], rendered)
            self.assertIn('data-polymarket-freshness', rendered)
            self.assertIn(OBSERVED, rendered)
            row.update(implied_probability=None, status="unavailable_price")
            rendered = reference.render_polymarket({"polymarket": row}, lang)
            self.assertIn(unavailable, rendered)
            self.assertNotIn("<strong>0.0%", rendered)

    def test_published_pages_and_manifest_integration(self):
        import build_publication_manifest as manifest
        payload = json.loads((ROOT / "candidate_polymarket.json").read_text(encoding="utf-8"))
        contract.validate_candidate_polymarket(payload, mapping=self.mapping, candidate_ids=self.ids)
        published = json.loads((ROOT / "publication_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(published["lanes"]["candidate_polymarket"]["valid"])
        for path in (ROOT / "candidates/marine-le-pen/index.html", ROOT / "en/candidates/marine-le-pen/index.html"):
            html = path.read_text(encoding="utf-8")
            self.assertLess(html.index('id="attention"'), html.index('id="polymarket-label"'))
            self.assertIn('id="polymarket-label"', html)
        for path in (ROOT / "index.html", ROOT / "en/index.html", ROOT / "candidates/index.html"):
            self.assertNotIn('id="polymarket-label"', path.read_text(encoding="utf-8"))

    def test_frontend_freshness_with_clock(self):
        # Execute the exact freshness helper in the existing Node UI-test style.
        script = r'''
const fs = require('fs'); const vm = require('vm');
const source = fs.readFileSync('assets/candidate-page.js','utf8');
const helper = source.slice(source.indexOf('  const updatePolymarketFreshness'), source.indexOf('  window.setInterval'));
const results = []; let requests = 0;
const now = Date.parse('2026-10-17T12:00:00Z');
class Clock extends Date { static now() { return now; } }
for (const lang of ['fr','en']) for (const age of [1,48,72]) for (const metadataAge of [1,720,null,undefined]) {
 const dataset = {observedAt:new Date(now-age*3600000).toISOString(),staleAfterHours:'48'};
 if (metadataAge !== undefined) dataset.sourceUpdatedAt = metadataAge === null
   ? null : new Date(now-metadataAge*3600000).toISOString();
 const row = {dataset};
 const fetch = () => { requests++; throw new Error('unexpected browser/provider request'); };
 vm.runInNewContext(helper,{Date:Clock,Number,fetch,window:{fetch},document:{documentElement:{lang},querySelectorAll(){return [row]}}});
 results.push({lang,age,metadataAge:metadataAge ?? null,state:row.dataset.state,text:row.textContent});
}
process.stdout.write(JSON.stringify({results,requests}));
'''
        result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                                text=True, encoding="utf-8", check=True)
        output = json.loads(result.stdout)
        self.assertEqual(output["requests"], 0)
        self.assertEqual(len(output["results"]), 24)
        for row in output["results"]:
            with self.subTest(**row):
                stale = row["age"] > 48
                self.assertEqual(row["state"], "stale" if stale else "recent")
                self.assertIn(
                    ("ancienne" if stale else "récente") if row["lang"] == "fr"
                    else ("Stale" if stale else "Recent"), row["text"]
                )

    def test_upstream_metadata_preserved_in_artifact_and_candidate_projection(self):
        import build_candidate_reference as reference
        row = self.row()
        self.assertEqual(row["source_updated_at"], self.event["markets"][0]["updatedAt"])
        self.assertEqual(self.build()["source_updated_at"], self.event["updatedAt"])
        published = json.loads((ROOT / "candidate_polymarket.json").read_text(encoding="utf-8"))
        projection = reference.build_projection(reference.load_sources(ROOT), ROOT)
        source_row = contract.candidate_record(published, "marine-le-pen")
        self.assertIn("source_updated_at", projection["polymarket"])
        self.assertEqual(projection["polymarket"]["source_updated_at"], source_row["source_updated_at"])
        self.assertIsNotNone(projection["polymarket"]["source_updated_at"])

    def test_recent_unmapped_candidate_remains_unavailable(self):
        import build_candidate_reference as reference
        row = self.row("anasse-kazib")
        row.update(observed_at=OBSERVED, stale_after_hours=48)
        self.assertIsNone(row["source_updated_at"])
        self.assertIsNone(row["implied_probability"])
        for lang, label in [("fr", "Indisponible"), ("en", "Unavailable")]:
            rendered = reference.render_polymarket({"polymarket": row}, lang)
            self.assertIn(f"<strong>{label}</strong>", rendered)
            self.assertNotIn("<strong>0", rendered)
            self.assertNotIn("https://polymarket.com/", rendered)

    def test_workflow_collects_only_daily_or_manual_and_keeps_failures_hard(self):
        workflow = (ROOT / ".github/workflows/publish-candidate-family.yml").read_text(encoding="utf-8")
        step = workflow.split("- name: Collect candidate prediction-market evidence", 1)[1].split("- name:", 1)[0]
        self.assertIn("github.event_name == 'schedule'", step)
        self.assertIn("github.event_name == 'workflow_dispatch'", step)
        self.assertIn("python -B build_candidate_polymarket.py", step)
        self.assertNotIn("continue-on-error", step)
        self.assertNotIn("|| true", step)


if __name__ == "__main__":
    unittest.main()
