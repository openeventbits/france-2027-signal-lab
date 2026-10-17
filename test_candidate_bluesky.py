"""Offline synthetic Bluesky identity, transport, publication and no-UI contracts."""

import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import build_candidate_bluesky as builder
import candidate_bluesky as contract

ROOT = Path(__file__).resolve().parent
OBSERVED = "2026-10-17T12:00:00Z"
A, B = "did:plc:" + "a" * 24, "did:plc:" + "b" * 24


def fixture():
    return json.loads((ROOT / "test_fixtures/bluesky_api.json").read_text(encoding="utf-8"))


def fixture_mapping():
    return {"schema_version": "1.0", "accounts": [
        {"candidate_id": "marine-le-pen", "did": A, "reviewed_handle": "candidate-a.bsky.social",
         "verification_url": "https://example.test/candidate-a",
         "account_url": "https://bsky.app/profile/candidate-a.bsky.social"},
        {"candidate_id": "edouard-philippe", "did": B, "reviewed_handle": "candidate-b.bsky.social",
         "verification_url": "https://example.test/candidate-b",
         "account_url": "https://bsky.app/profile/candidate-b.bsky.social"},
    ]}


class FixtureClient:
    """No transport: tests cannot make live Bluesky calls."""
    def __init__(self, data=None):
        self.data = copy.deepcopy(data if data is not None else fixture())
        self.requests = {builder.PROFILES: 0, builder.RESOLVE: 0}
        self.calls = []

    def get(self, endpoint, **params):
        self.requests[endpoint] += 1
        self.calls.append((endpoint, params))
        if endpoint == builder.PROFILES:
            return {"profiles": [copy.deepcopy(row) for row in self.data["profiles"]
                                 if row["did"] in params["actors"]]}
        return {"did": next(row["did"] for row in self.data["profiles"] if row["handle"] == params["handle"])}


def fixture_payload(ids=None):
    return builder.build_candidate_bluesky(FixtureClient(), fixture_mapping(),
        ids or {"marine-le-pen", "edouard-philippe", "unmapped"}, OBSERVED)


def opt_out_label(**updates):
    return {"src": A, "uri": A, "val": "!no-unauthenticated", "cts": "2026-10-16T12:00:00Z", **updates}


class BlueskyContractTests(unittest.TestCase):
    def setUp(self):
        self.mapping, self.data = fixture_mapping(), fixture()
        self.ids = {"marine-le-pen", "edouard-philippe", "unmapped"}

    def build(self, client=None):
        return builder.build_candidate_bluesky(client or FixtureClient(self.data), self.mapping, self.ids, OBSERVED)

    def row(self, payload=None, cid="marine-le-pen"):
        return next(row for row in (payload or self.build())["candidates"] if row["candidate_id"] == cid)

    def test_valid_did_mapping(self):
        contract.validate_mapping(self.mapping, self.ids)

    def test_supported_did_methods_and_rejected_forms(self):
        self.assertTrue(contract.valid_did(A))
        self.assertTrue(contract.valid_did("did:web:candidate.test"))
        for value in ("did:plc:short", "did:plc:" + "0" * 24, "did:key:unknown", None, True):
            with self.subTest(value=value):
                self.assertFalse(contract.valid_did(value))

    def test_duplicate_candidate_mapping(self):
        self.mapping["accounts"][1]["candidate_id"] = "marine-le-pen"
        with self.assertRaises(contract.CandidateBlueskyError): self.build()

    def test_duplicate_did_mapping(self):
        self.mapping["accounts"][1]["did"] = A
        with self.assertRaises(contract.CandidateBlueskyError): self.build()

    def test_registry_mismatch(self):
        self.mapping["accounts"][0]["candidate_id"] = "outside-registry"
        with self.assertRaises(contract.CandidateBlueskyError): self.build()

    def test_invalid_mapping_handle(self):
        for handle in ("@candidate.bsky.social", "a..social", "a.123", "A.bsky.social", "handle.invalid", "a-.social"):
            with self.subTest(handle=handle):
                self.assertFalse(contract.valid_handle(handle))

    def test_mapping_url_must_identify_account(self):
        self.mapping["accounts"][0]["account_url"] = "https://bsky.app/profile/other.bsky.social"
        with self.assertRaises(contract.CandidateBlueskyError): self.build()

    def test_verification_url_rejects_credentials(self):
        self.mapping["accounts"][0]["verification_url"] = "https://secret@example.test/"
        with self.assertRaises(contract.CandidateBlueskyError): self.build()

    def test_unmapped_account_all_evidence_null(self):
        row = self.row(cid="unmapped")
        self.assertEqual(row["status"], "unavailable_no_account")
        self.assertTrue(all(row[key] is None for key in contract.ROW_KEYS - {"candidate_id", "status"}))

    def test_correct_profile_parse_and_no_unneeded_content(self):
        row = self.row()
        self.assertEqual((row["did"], row["handle"], row["display_name"]),
                         (A, "candidate-a.bsky.social", "Synthetic Candidate A"))
        self.assertEqual((row["followers_count"], row["follows_count"], row["posts_count"]), (12345, 123, 456))
        self.assertEqual(row["profile_url"], "https://bsky.app/profile/" + A)
        self.assertEqual(set(row), contract.ROW_KEYS)
        self.assertNotIn("description", json.dumps(self.build()))
        self.assertNotIn("avatar", json.dumps(self.build()))

    def test_zero_is_valid_observed_count(self):
        row = self.row(cid="edouard-philippe")
        self.assertEqual(row["status"], "observed")
        self.assertEqual(row["followers_count"], 0)
        self.assertIsNone(row["display_name"])

    def test_unrequested_or_duplicate_returned_did(self):
        for profiles in ([self.data["profiles"][0], self.data["profiles"][0]],
                         [{**self.data["profiles"][0], "did": "did:plc:" + "c" * 24}]):
            with self.subTest(profiles=profiles):
                with self.assertRaises(contract.CandidateBlueskyError):
                    builder.parse_profiles({"profiles": profiles}, {A, B}, OBSERVED)

    def test_observed_handle_resolving_to_different_did_fails(self):
        client = FixtureClient()
        original = client.get
        client.get = lambda endpoint, **params: {"did": B} if endpoint == builder.RESOLVE else original(endpoint, **params)
        with self.assertRaises(contract.CandidateBlueskyError): self.build(client)

    def test_handle_update_with_stable_did_is_normal(self):
        self.data["profiles"][0]["handle"] = "new-handle.candidate.test"
        self.assertEqual(self.row()["handle"], "new-handle.candidate.test")
        self.assertEqual(self.row()["did"], A)

    def test_invalid_observed_handle(self):
        self.data["profiles"][0]["handle"] = "handle.invalid"
        with self.assertRaises(contract.CandidateBlueskyError): self.build()

    def test_malformed_negative_and_unsafe_counts(self):
        for key in ("followersCount", "followsCount", "postsCount"):
            for value in (-1, 1.5, "12", True, None, 2**53, float("nan")):
                with self.subTest(key=key, value=value):
                    data = fixture()
                    data["profiles"][0][key] = value
                    with self.assertRaises(contract.CandidateBlueskyError): self.build(FixtureClient(data))

    def test_missing_count_fails(self):
        del self.data["profiles"][0]["postsCount"]
        with self.assertRaises(contract.CandidateBlueskyError): self.build()

    def test_missing_account_fails_whole_snapshot(self):
        self.data["profiles"].pop()
        with self.assertRaisesRegex(contract.CandidateBlueskyError, "missing/inaccessible"): self.build()

    def test_malformed_profile_response(self):
        for payload in ({}, {"profiles": None}, {"profiles": [None]}):
            with self.subTest(payload=payload):
                with self.assertRaises(contract.CandidateBlueskyError): builder.parse_profiles(payload, {A}, OBSERVED)

    def test_public_web_opt_out_suppresses_every_profile_field(self):
        self.data["profiles"][0]["labels"] = [opt_out_label()]
        self.data["profiles"][0]["followersCount"] = "must not be consumed"
        client = FixtureClient(self.data)
        row = self.row(self.build(client))
        self.assertEqual(row, contract.empty_record("marine-le-pen", {"did": A}, status="unavailable_public_web_opt_out"))
        self.assertEqual(client.requests[builder.RESOLVE], 1)

    def test_profile_record_opt_out_is_respected(self):
        self.data["profiles"][0]["labels"] = [opt_out_label(uri=f"at://{A}/app.bsky.actor.profile/self")]
        self.assertEqual(self.row()["status"], "unavailable_public_web_opt_out")

    def test_negated_and_expired_opt_out(self):
        for update in ({"neg": True}, {"exp": OBSERVED}):
            with self.subTest(update=update):
                self.data["profiles"][0]["labels"] = [opt_out_label(**update)]
                self.assertEqual(self.row()["status"], "observed")

    def test_latest_opt_out_event_wins_for_same_source_target(self):
        self.data["profiles"][0]["labels"] = [opt_out_label(), opt_out_label(neg=True, cts="2026-10-17T11:00:00Z")]
        self.assertEqual(self.row()["status"], "observed")
        self.data["profiles"][0]["labels"].reverse()
        self.assertEqual(self.row()["status"], "observed")

    def test_malformed_opt_out_labels_fail_closed(self):
        for labels in (None, ["bad"], [opt_out_label(neg="false")], [opt_out_label(uri=B)],
                       [opt_out_label(cts="bad")], [opt_out_label(), opt_out_label(neg=True)]):
            with self.subTest(labels=labels):
                self.data["profiles"][0]["labels"] = labels
                with self.assertRaises(contract.CandidateBlueskyError): self.build()

    def test_complete_registry_coverage(self):
        ids = {row["candidate_id"] for row in json.loads((ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8"))["candidates"]}
        payload = fixture_payload(ids)
        contract.validate_candidate_bluesky(payload, mapping=self.mapping, candidate_ids=ids)
        self.assertEqual(len(payload["candidates"]), len(ids))
        payload["candidates"].pop()
        with self.assertRaises(contract.CandidateBlueskyError): contract.validate_candidate_bluesky(payload, candidate_ids=ids)

    def test_deterministic_output_and_input_not_mutated(self):
        before = copy.deepcopy(self.mapping)
        first = self.build()
        self.mapping["accounts"].reverse()
        self.data["profiles"].reverse()
        self.assertEqual(first, self.build())
        self.assertEqual(sorted(self.mapping["accounts"], key=lambda row: row["candidate_id"]),
                         sorted(before["accounts"], key=lambda row: row["candidate_id"]))

    def test_artifact_validation_rejects_unknown_fields_status_and_identity(self):
        mutations = [lambda p: p.update(extra=True), lambda p: self.row(p).update(status="unknown"),
                     lambda p: self.row(p).update(did=B), lambda p: self.row(p).update(followers_count=-1),
                     lambda p: p.update(generated_at="2026-10-16T12:00:00Z")]
        for mutate in mutations:
            payload = self.build()
            mutate(payload)
            with self.assertRaises(contract.CandidateBlueskyError):
                contract.validate_candidate_bluesky(payload, mapping=self.mapping, candidate_ids=self.ids)

    def test_unavailable_cannot_publish_metrics(self):
        payload = self.build()
        self.row(payload).update(status="unavailable_public_web_opt_out")
        with self.assertRaises(contract.CandidateBlueskyError): contract.validate_candidate_bluesky(payload)

    def test_missing_account_contract_without_fabricated_values(self):
        payload = self.build()
        payload["candidates"][1] = contract.empty_record("marine-le-pen", {"did": A})
        contract.validate_candidate_bluesky(payload, mapping=self.mapping)

    def test_projection_observed_unmapped_and_opt_out(self):
        self.data["profiles"][0]["labels"] = [opt_out_label()]
        payload = self.build()
        for cid in self.ids:
            row = contract.candidate_projection(payload, cid)
            contract.validate_candidate_bluesky_projection(row, cid)
            self.assertEqual(row["observed_at"], OBSERVED)
        with self.assertRaises(contract.CandidateBlueskyError): contract.candidate_projection(payload, "missing")

    def test_profile_batches_of_25_with_pinned_dids(self):
        mapping = {"schema_version": "1.0", "accounts": []}
        data = {"profiles": []}
        for i in range(26):
            did = "did:plc:" + "a" * 22 + chr(97 + i // 26) + chr(97 + i % 26)
            handle = f"candidate-{i}.bsky.social"
            mapping["accounts"].append(dict(candidate_id=f"candidate-{i}", did=did, reviewed_handle=handle,
                verification_url=f"https://example.test/{i}", account_url=f"https://bsky.app/profile/{handle}"))
            data["profiles"].append(dict(did=did, handle=handle, followersCount=0, followsCount=0, postsCount=0))
        client = FixtureClient(data)
        builder.build_candidate_bluesky(client, mapping, {row["candidate_id"] for row in mapping["accounts"]}, OBSERVED)
        batches = [params["actors"] for endpoint, params in client.calls if endpoint == builder.PROFILES]
        self.assertEqual([len(batch) for batch in batches], [25, 1])
        self.assertTrue(all(actor.startswith("did:") for batch in batches for actor in batch))


class BlueskyTransportTests(unittest.TestCase):
    def response(self, payload=None, raw=None):
        response = Mock(status=200)
        response.read.return_value = raw if raw is not None else json.dumps(payload or {"profiles": []}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_exact_public_host_no_auth_and_repeated_actor_parameters(self):
        opener = Mock(return_value=self.response())
        client = builder.BlueskyClient(opener=opener, sleep=Mock())
        client.get(builder.PROFILES, actors=[A, B])
        request = opener.call_args.args[0]
        self.assertEqual(urlsplit(request.full_url).netloc, "public.api.bsky.app")
        self.assertEqual(parse_qs(urlsplit(request.full_url).query)["actors"], [A, B])
        self.assertFalse(any(key.lower() == "authorization" for key in request.headers))
        self.assertEqual(opener.call_args.kwargs["timeout"], 20)

    def test_http_400_and_404_fail_without_retry(self):
        for code in (400, 401, 403, 404):
            with self.subTest(code=code):
                opener, sleep = Mock(side_effect=HTTPError("private-url", code, "private-reason", {}, None)), Mock()
                with self.assertRaisesRegex(contract.CandidateBlueskyError, f"HTTP failure: {code}"):
                    builder.BlueskyClient(opener=opener, sleep=sleep).get(builder.PROFILES, actors=[A])
                self.assertEqual(opener.call_count, 1)
                sleep.assert_not_called()

    def test_429_retries_with_capped_retry_after(self):
        opener = Mock(side_effect=[HTTPError("url", 429, "reason", {"Retry-After": "999"}, None), self.response()])
        sleep = Mock()
        builder.BlueskyClient(opener=opener, sleep=sleep).get(builder.PROFILES, actors=[A])
        self.assertEqual(opener.call_count, 2)
        sleep.assert_called_once_with(30)

    def test_retryable_5xx_recovers(self):
        for code in (500, 502, 503, 504):
            with self.subTest(code=code):
                opener = Mock(side_effect=[HTTPError("url", code, "reason", {}, None), self.response()])
                builder.BlueskyClient(opener=opener, sleep=Mock()).get(builder.PROFILES, actors=[A])
                self.assertEqual(opener.call_count, 2)

    def test_timeout_network_and_exhausted_429_are_bounded_and_safe(self):
        for error in (TimeoutError("private-data"), URLError("private-data"),
                      HTTPError("private-url", 429, "private-data", {}, None)):
            with self.subTest(error=type(error).__name__):
                opener, sleep = Mock(side_effect=error), Mock()
                with self.assertRaises(contract.CandidateBlueskyError) as caught:
                    builder.BlueskyClient(opener=opener, sleep=sleep).get(builder.PROFILES, actors=[A])
                self.assertEqual(opener.call_count, 3)
                self.assertEqual(sleep.call_count, 2)
                self.assertNotIn("private", str(caught.exception))

    def test_malformed_json_schema_and_size_bound(self):
        for raw in (b"{bad", b"\xff", b"[]", b'{"error":"bad"}', b"x" * (builder.MAX_BYTES + 1)):
            with self.subTest(length=len(raw)):
                opener = Mock(return_value=self.response(raw=raw))
                with self.assertRaises(contract.CandidateBlueskyError):
                    builder.BlueskyClient(opener=opener, sleep=Mock()).get(builder.PROFILES, actors=[A])
                self.assertEqual(opener.call_count, 1)

    def test_unsupported_endpoint_rejected(self):
        with self.assertRaises(contract.CandidateBlueskyError): builder.BlueskyClient(opener=Mock()).get("searchActors")

    def test_failure_preserves_previous_artifact_bytes(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            output, mapping = root / "snapshot.json", root / "mapping.json"
            previous = json.dumps(fixture_payload()).encode()
            output.write_bytes(previous)
            mapping.write_text(json.dumps(fixture_mapping()), encoding="utf-8")
            for client in (FixtureClient({"profiles": []}),
                           builder.BlueskyClient(opener=Mock(side_effect=TimeoutError()), sleep=Mock())):
                with self.assertRaises(contract.CandidateBlueskyError):
                    builder.collect(output, mapping_path=mapping, client=client, observed_at=OBSERVED)
                self.assertEqual(output.read_bytes(), previous)

    def test_cli_failure_diagnostics_are_generic(self):
        with patch.object(builder, "collect", side_effect=contract.CandidateBlueskyError("private-data")), \
                patch("sys.argv", ["build_candidate_bluesky.py"]), redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(builder.main(), 1)
        self.assertNotIn("private-data", stream.getvalue())
        self.assertIn("prior artifact retained", stream.getvalue())


class BlueskyPublicationTests(unittest.TestCase):
    def test_manifest_independent_lane_hashes_and_observation_time(self):
        import build_publication_manifest as manifest
        self.assertEqual(manifest.SCHEMA_VERSION, "1.5")
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            for filename, payload in (("candidate_bluesky.json", fixture_payload()),
                                      ("bluesky_candidate_accounts.json", fixture_mapping())):
                (root / filename).write_text(json.dumps(payload), encoding="utf-8")
            lane, _ = manifest._build_lane(root, "candidate_bluesky")
            self.assertTrue(lane["valid"])
            self.assertEqual(lane["data_as_of"], OBSERVED)
            self.assertEqual(lane["record_count"], 3)
            self.assertEqual(lane["sha256"], hashlib.sha256((root / "candidate_bluesky.json").read_bytes()).hexdigest())
            self.assertEqual(lane["related_files"][0]["sha256"], hashlib.sha256((root / "bluesky_candidate_accounts.json").read_bytes()).hexdigest())

    def test_manifest_full_registry_coverage_and_mapping_fail_closed(self):
        import build_publication_manifest as manifest
        from test_publication_manifest import complete_inputs
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            complete_inputs(root)
            payload = json.loads((root / "candidate_bluesky.json").read_text(encoding="utf-8"))
            payload["candidates"].pop()
            (root / "candidate_bluesky.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(manifest.ManifestError): manifest.build_manifest(root, published_at=OBSERVED)
            complete_inputs(root)
            (root / "bluesky_candidate_accounts.json").unlink()
            with self.assertRaises(manifest.ManifestError): manifest.build_manifest(root, published_at=OBSERVED)

    def test_candidate_projection_and_public_signal_card(self):
        import build_candidate_reference as reference
        sources = {key: json.loads((ROOT / name).read_text(encoding="utf-8"))
                   for key, name in reference.SOURCE_FILES.items()
                   if key not in {"candidate_bluesky", "bluesky_candidate_accounts"}}
        ids = {row["candidate_id"] for row in sources["candidate_candidacy_status"]["candidates"]}
        sources.update(candidate_bluesky=fixture_payload(ids), bluesky_candidate_accounts=fixture_mapping())
        projected = reference.build_projection(sources, ROOT)
        self.assertEqual(projected["bluesky"]["followers_count"], 12345)
        self.assertNotIn("bluesky", projected["attention"])
        self.assertNotIn("bluesky", projected["youtube"])
        self.assertNotIn("bluesky", projected["polymarket"])
        metrics = reference.derive_hud_metrics(sources)
        without = copy.deepcopy(projected)
        without.pop("bluesky")
        for lang in ("fr", "en"):
            rendered = reference.render_html(projected, metrics, lang=lang)
            without_html = reference.render_html(without, metrics, lang=lang)
            self.assertNotEqual(rendered, without_html)
            self.assertEqual(rendered.count(b'data-provider="'), 3)
            card = rendered.split(b'data-provider="bluesky"', 1)[1].split(b'</article>', 1)[0]
            self.assertIn(("12\u202f345" if lang == "fr" else "12,345").encode(), card)
            self.assertIn(projected["bluesky"]["profile_url"].encode(), card)
            unavailable = without_html.split(b'data-provider="bluesky"', 1)[1].split(b'</article>', 1)[0]
            self.assertNotIn(b'href=', unavailable)

    def test_workflow_collection_gated_and_publication_time_fallback(self):
        workflow = (ROOT / ".github/workflows/publish-candidate-family.yml").read_text(encoding="utf-8")
        start = workflow.index("- name: Collect candidate Bluesky evidence")
        end = workflow.index("- name: Build and validate candidate publication")
        step = workflow[start:end]
        self.assertIn("steps.dependencies.outputs.ready == 'true'", step)
        self.assertIn("github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'", step)
        self.assertLess(step.index("test_candidate_bluesky"), step.index("python -B build_candidate_bluesky.py"))
        self.assertNotIn("secrets.", step)
        self.assertNotIn("continue-on-error", step)
        self.assertIn("steps.bluesky.outputs.published_at || steps.youtube.outputs.published_at || steps.polymarket.outputs.published_at", workflow)
        self.assertGreaterEqual(workflow.count("candidate_bluesky.json candidate_polymarket.json"), 5)

    def test_general_validation_stays_offline(self):
        workflow = (ROOT / ".github/workflows/validate-dashboard.yml").read_text(encoding="utf-8")
        self.assertIn("test_candidate_bluesky", workflow)
        self.assertNotIn("build_candidate_bluesky.py", workflow)
        self.assertNotIn("public.api.bsky.app", workflow)

    def test_other_provider_artifacts_unchanged_by_collection(self):
        paths = [ROOT / "candidate_polymarket.json", ROOT / "candidate_youtube.json"]
        before = [path.read_bytes() for path in paths]
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            mapping = Path(tmp) / "mapping.json"
            mapping.write_text(json.dumps(fixture_mapping()), encoding="utf-8")
            builder.collect(Path(tmp) / "bluesky.json", mapping_path=mapping, client=FixtureClient(), observed_at=OBSERVED)
        self.assertEqual(before, [path.read_bytes() for path in paths])


if __name__ == "__main__":
    unittest.main()
