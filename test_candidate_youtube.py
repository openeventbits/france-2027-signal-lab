"""Offline YouTube contracts, bounded collector, publication and no-UI regression tests."""

import copy
import hashlib
import io
import json
import os
import subprocess
import tempfile
import traceback
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import build_candidate_youtube as builder
import candidate_youtube as contract

ROOT = Path(__file__).resolve().parent
OBSERVED = "2026-10-17T12:00:00Z"
SECRET = "synthetic-test-credential-DO-NOT-LOG"
A, B = "UC" + "a" * 22, "UC" + "b" * 22


def fixture():
    return json.loads((ROOT / "test_fixtures/youtube_api.json").read_text(encoding="utf-8"))


def fixture_mapping():
    return {"schema_version": "1.0", "channels": [
        {"candidate_id": "marine-le-pen", "channel_id": A, "verification_url": "https://example.test/candidate-a"},
        {"candidate_id": "edouard-philippe", "channel_id": B, "verification_url": "https://example.test/candidate-b"},
    ]}


class FixtureClient:
    """No transport exists in this client: unit tests cannot call Google."""
    def __init__(self, data=None):
        self.data = data or fixture()
        self.requests = {k: 0 for k in builder.PARTS}
        self.calls = []

    def get(self, endpoint, **params):
        self.calls.append((endpoint, params))
        self.requests[endpoint] += 1
        if endpoint == "playlistItems":
            return copy.deepcopy(self.data["uploads"] if params["playlistId"] == "UU" + "a" * 22 else {"items": []})
        if endpoint == "videos":
            return {"items": copy.deepcopy([v for v in self.data["videos"]["items"]
                                           if v["id"] in params["id"].split(",")])}
        return copy.deepcopy(self.data[endpoint])

    def assert_secret_absent(self, value):
        contract.require(SECRET not in json.dumps(value), "credential contamination")


def fixture_payload(ids=None):
    ids = ids or {"marine-le-pen", "edouard-philippe", "unmapped"}
    return builder.build_candidate_youtube(FixtureClient(), fixture_mapping(), ids, OBSERVED)


class YouTubeTests(unittest.TestCase):
    def setUp(self):
        self.data, self.mapping = fixture(), fixture_mapping()
        self.ids = {"marine-le-pen", "edouard-philippe", "unmapped"}

    def build(self, client=None):
        return builder.build_candidate_youtube(client or FixtureClient(self.data), self.mapping, self.ids, OBSERVED)

    def row(self, cid="marine-le-pen"):
        return next(r for r in self.build()["candidates"] if r["candidate_id"] == cid)

    def test_valid_mapping(self):
        contract.validate_mapping(self.mapping, self.ids)

    def test_duplicate_candidate(self):
        self.mapping["channels"][1]["candidate_id"] = "marine-le-pen"
        with self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_duplicate_channel(self):
        self.mapping["channels"][1]["channel_id"] = A
        with self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_candidate_outside_registry(self):
        self.ids.remove("marine-le-pen")
        with self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_invalid_stable_identity(self):
        for value in ("@candidate", "a name", None, A + "x"):
            self.mapping["channels"][0]["channel_id"] = value
            with self.subTest(value=value), self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_unmapped_candidate(self):
        self.assertEqual(self.row("unmapped"), contract.empty_record("unmapped"))

    def test_no_mapped_channels_no_calls(self):
        self.mapping["channels"] = []
        client = FixtureClient()
        self.assertTrue(all(r["status"] == "unavailable_no_channel" for r in self.build(client)["candidates"]))
        self.assertEqual(client.calls, [])

    def test_wrong_returned_channel(self):
        self.data["channels"]["items"][0]["id"] = "UC" + "z" * 22
        with self.assertRaisesRegex(contract.CandidateYouTubeError, "returned channel"): self.build()

    def test_missing_mapped_channel_fails_closed(self):
        self.data["channels"]["items"].pop()
        with self.assertRaisesRegex(contract.CandidateYouTubeError, "missing/inaccessible"): self.build()

    def test_duplicate_returned_channel(self):
        self.data["channels"]["items"].append(self.data["channels"]["items"][0])
        with self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_channels_list_parse(self):
        self.assertEqual(self.row()["status"], "observed")
        self.assertEqual(self.row()["channel_id"], A)

    def test_channel_title(self):
        self.assertEqual(self.row()["channel_title"], "Synthetic candidate channel")

    def test_uploads_playlist(self):
        self.assertEqual(self.row()["uploads_playlist_id"], "UU" + "a" * 22)

    def test_missing_uploads_playlist(self):
        del self.data["channels"]["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        with self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_subscriber_count_preserved(self):
        self.assertEqual(self.row()["subscriber_count"], 123000)

    def test_hidden_subscribers(self):
        self.assertTrue(self.row("edouard-philippe")["hidden_subscriber_count"])

    def test_hidden_is_null_not_zero(self):
        self.assertIsNone(self.row("edouard-philippe")["subscriber_count"])

    def test_hidden_supplied_count_stays_null(self):
        self.data["channels"]["items"][1]["statistics"]["subscriberCount"] = "100"
        self.assertIsNone(self.row("edouard-philippe")["subscriber_count"])

    def test_visibility_flag_required(self):
        self.data["channels"]["items"][0]["statistics"]["hiddenSubscriberCount"] = "false"
        with self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_channel_view_count(self):
        self.assertEqual(self.row()["channel_view_count"], 9876543)

    def test_public_video_count(self):
        self.assertEqual(self.row()["public_video_count"], 300)

    def test_malformed_counts(self):
        for value in (None, "", "1.2", "1e3", "NaN", True, 1, {}, " 1", "+1", "١"):
            self.data["channels"]["items"][0]["statistics"]["viewCount"] = value
            with self.subTest(value=value), self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_negative_count(self):
        with self.assertRaises(contract.CandidateYouTubeError): contract.count("-1")

    def test_integer_safety(self):
        self.assertEqual(contract.count(str(2**53 - 1)), 2**53 - 1)
        for value in (str(2**53), "9" * 400):
            with self.assertRaises(contract.CandidateYouTubeError): contract.count(value)

    def test_playlist_items_parse(self):
        self.assertEqual({v["video_id"] for v in self.row()["recent_videos"]}, {"a" * 11, "b" * 11})

    def test_video_publication_field_used(self):
        self.assertEqual(self.row()["recent_videos"][0]["published_at"], "2026-10-16T12:00:00Z")

    def test_playlist_addition_time_never_used(self):
        for item in self.data["uploads"]["items"]: item["snippet"]["publishedAt"] = "not a video publication time"
        self.assertEqual(self.row()["uploads_last_7d"], 2)

    def test_seven_day_boundary_inclusive(self):
        self.assertEqual(self.row()["recent_videos"][-1]["published_at"], "2026-10-10T12:00:00Z")
        self.assertNotIn("c" * 11, [v["video_id"] for v in self.row()["recent_videos"]])

    def test_upper_boundary_and_future(self):
        self.data["uploads"]["items"][0]["contentDetails"]["videoPublishedAt"] = OBSERVED
        self.assertEqual(self.row()["uploads_last_7d"], 2)
        self.data["uploads"]["items"][0]["contentDetails"]["videoPublishedAt"] = "2026-10-17T12:00:01Z"
        self.assertEqual(self.row()["uploads_last_7d"], 1)

    def test_upload_count(self):
        self.assertEqual(self.row()["uploads_last_7d"], 2)

    def test_latest_upload(self):
        self.assertEqual(self.row()["latest_upload_at"], "2026-10-16T12:00:00Z")

    def test_latest_upload_can_be_older_than_window(self):
        self.data["uploads"]["items"] = [self.data["uploads"]["items"][-1]]
        self.assertEqual(self.row()["uploads_last_7d"], 0)
        self.assertEqual(self.row()["latest_upload_at"], "2026-10-10T11:59:59Z")

    def test_deterministic_output(self):
        first = self.build()
        self.data["channels"]["items"].reverse()
        self.data["uploads"]["items"].reverse()
        self.data["videos"]["items"].reverse()
        self.mapping["channels"].reverse()
        self.assertEqual(json.dumps(first), json.dumps(self.build()))

    def test_pagination_continues_after_old_item(self):
        client = Mock()
        client.get.side_effect = [
            {"items": [self.data["uploads"]["items"][-1]], "nextPageToken": "next"},
            {"items": self.data["uploads"]["items"][:2]},
        ]
        videos, complete, latest = builder.collect_uploads(client, "UU" + "a" * 22, A, OBSERVED)
        self.assertTrue(complete)
        self.assertEqual(len(videos), 2)
        self.assertEqual(client.get.call_args.kwargs["pageToken"], "next")
        self.assertEqual(latest, "2026-10-16T12:00:00Z")

    def test_pagination_bound(self):
        client = Mock()
        client.get.return_value = {"items": self.data["uploads"]["items"], "nextPageToken": "next"}
        videos, complete, latest = builder.collect_uploads(client, "UU" + "a" * 22, A, OBSERVED, max_pages=1)
        self.assertFalse(complete)
        self.assertIsNone(latest)
        self.assertEqual(len(videos), 2)
        self.assertEqual(client.get.call_count, 1)

    def test_incomplete_window_count_is_null(self):
        client = FixtureClient(self.data)
        original = builder.collect_uploads
        self.data["uploads"]["nextPageToken"] = "next"
        with patch.object(builder, "collect_uploads", side_effect=lambda *a: original(*a, max_pages=1)):
            row = next(r for r in self.build(client)["candidates"] if r["candidate_id"] == "marine-le-pen")
        self.assertFalse(row["recent_window_complete"])
        self.assertIsNone(row["uploads_last_7d"])
        self.assertIsNone(row["latest_upload_at"])
        self.assertTrue(row["recent_video_metrics_complete"])

    def test_pagination_cycle_and_failure(self):
        for responses in (
            [{"items": [], "nextPageToken": "same"}] * 2,
            [{"items": [], "nextPageToken": "next"}, contract.CandidateYouTubeError("failure")],
        ):
            client = Mock()
            client.get.side_effect = responses
            with self.assertRaises(contract.CandidateYouTubeError): builder.collect_uploads(client, "UU" + "a" * 22, A, OBSERVED)

    def test_missing_publication_date_incomplete(self):
        del self.data["uploads"]["items"][0]["contentDetails"]["videoPublishedAt"]
        self.assertFalse(self.row()["recent_window_complete"])
        self.assertIsNone(self.row()["uploads_last_7d"])

    def test_malformed_timestamp(self):
        for value in ("yesterday", "2026-02-30T00:00:00Z", "2026-10-16T12:00:00", 1):
            self.data["uploads"]["items"][0]["contentDetails"]["videoPublishedAt"] = value
            with self.subTest(value=value), self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_upload_owner_validation(self):
        self.data["uploads"]["items"][0]["snippet"]["videoOwnerChannelId"] = B
        with self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_videos_batched(self):
        client = FixtureClient()
        self.build(client)
        calls = [p for endpoint, p in client.calls if endpoint == "videos"]
        self.assertEqual(calls, [{"id": "aaaaaaaaaaa,bbbbbbbbbbb"}])
        self.assertEqual([len(b) for b in builder.batches([str(i) for i in range(111)])], [50, 50, 11])

    def test_channels_batched(self):
        client = FixtureClient()
        self.build(client)
        self.assertEqual(client.calls[0], ("channels", {"id": A + "," + B, "maxResults": 50}))

    def test_video_view_count(self):
        self.assertEqual(self.row()["recent_videos"][0]["view_count"], 12345)
        self.assertEqual(self.row()["recent_videos"][1]["view_count"], 0)

    def test_missing_video_null(self):
        self.data["videos"]["items"].pop(0)
        self.assertIsNone(self.row()["recent_videos"][0]["view_count"])
        self.assertFalse(self.row()["recent_video_metrics_complete"])
        self.assertTrue(self.row()["recent_window_complete"])

    def test_missing_video_statistics_null(self):
        self.data["videos"]["items"][0].pop("statistics")
        self.assertIsNone(self.row()["recent_videos"][0]["view_count"])

    def test_malformed_video_statistics(self):
        self.data["videos"]["items"][0]["statistics"]["viewCount"] = "bad"
        with self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_wrong_video_owner(self):
        self.data["videos"]["items"][0]["snippet"]["channelId"] = B
        with self.assertRaises(contract.CandidateYouTubeError): self.build()

    def test_bad_publication_counts_and_completeness_rejected(self):
        for field, value in (("uploads_last_7d", 3), ("recent_window_complete", False),
                             ("subscriber_count", True), ("recent_video_metrics_complete", False)):
            payload = self.build()
            row = next(r for r in payload["candidates"] if r["candidate_id"] == "marine-le-pen")
            row[field] = value
            with self.subTest(field=field), self.assertRaises(contract.CandidateYouTubeError):
                contract.validate_candidate_youtube(payload, mapping=self.mapping, candidate_ids=self.ids)

    def test_complete_window_cannot_omit_latest_recent_video(self):
        payload = self.build()
        row = next(r for r in payload["candidates"] if r["candidate_id"] == "marine-le-pen")
        row.update(recent_videos=[], uploads_last_7d=0)
        with self.assertRaisesRegex(contract.CandidateYouTubeError, "absent"):
            contract.validate_candidate_youtube(payload)

    def test_registry_coverage_exact(self):
        ids = {r["candidate_id"] for r in json.loads((ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8"))["candidates"]}
        payload = fixture_payload(ids)
        contract.validate_candidate_youtube(payload, mapping=self.mapping, candidate_ids=ids)
        self.assertEqual({r["candidate_id"] for r in payload["candidates"]}, ids)
        payload["candidates"].pop()
        with self.assertRaises(contract.CandidateYouTubeError): contract.validate_candidate_youtube(payload, candidate_ids=ids)

    def test_observed_projection(self):
        row = contract.candidate_projection(self.build(), "marine-le-pen")
        contract.validate_candidate_youtube_projection(row, "marine-le-pen")
        self.assertEqual(row["observed_at"], OBSERVED)
        self.assertEqual(row["subscriber_count"], 123000)

    def test_unmapped_projection(self):
        row = contract.candidate_projection(self.build(), "unmapped")
        contract.validate_candidate_youtube_projection(row, "unmapped")
        self.assertIsNone(row["subscriber_count"])
        self.assertIsNone(row["channel_url"])

    def test_hidden_projection(self):
        row = contract.candidate_projection(self.build(), "edouard-philippe")
        contract.validate_candidate_youtube_projection(row, "edouard-philippe")
        self.assertTrue(row["hidden_subscriber_count"])
        self.assertIsNone(row["subscriber_count"])

    def test_missing_state_has_no_fake_metrics(self):
        payload = self.build()
        row = contract.empty_record("marine-le-pen", self.mapping["channels"][0])
        payload["candidates"] = [row if r["candidate_id"] == "marine-le-pen" else r for r in payload["candidates"]]
        contract.validate_candidate_youtube(payload, mapping=self.mapping, candidate_ids=self.ids)
        self.assertIsNone(row["subscriber_count"])

    def test_production_mapping_reviewed_registry(self):
        registry = json.loads((ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8"))
        mapping = json.loads((ROOT / "youtube_candidate_channels.json").read_text(encoding="utf-8"))
        contract.validate_mapping(mapping, {r["candidate_id"] for r in registry["candidates"]})
        self.assertGreater(len(mapping["channels"]), 0)

    def test_manifest_lane_fixture_and_hashes(self):
        import build_publication_manifest as manifest
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            (root / "candidate_youtube.json").write_text(json.dumps(self.build()), encoding="utf-8")
            (root / "youtube_candidate_channels.json").write_text(json.dumps(self.mapping), encoding="utf-8")
            lane, _ = manifest._build_lane(root, "candidate_youtube")
            self.assertTrue(lane["valid"])
            self.assertEqual(lane["data_as_of"], OBSERVED)
            self.assertEqual(lane["record_count"], 3)
            self.assertEqual(lane["sha256"], hashlib.sha256((root / "candidate_youtube.json").read_bytes()).hexdigest())
            self.assertEqual(lane["related_files"][0]["sha256"], hashlib.sha256((root / "youtube_candidate_channels.json").read_bytes()).hexdigest())

    def test_candidate_builder_projection_and_public_signal_card(self):
        import build_candidate_reference as reference
        sources = {k: json.loads((ROOT / name).read_text(encoding="utf-8")) for k, name in reference.SOURCE_FILES.items()
                   if k not in {"candidate_youtube", "youtube_candidate_channels"}}
        ids = {r["candidate_id"] for r in sources["candidate_candidacy_status"]["candidates"]}
        sources.update(candidate_youtube=fixture_payload(ids), youtube_candidate_channels=self.mapping)
        import candidate_youtube_history as history_contract
        histories = reference.load_signal_histories(ROOT)
        fixture_history = history_contract.build_history(sources["candidate_youtube"],
            sources["youtube_candidate_channels"], ids)
        histories["youtube"] = {r["candidate_id"]: r for r in fixture_history["candidates"]}
        projected = reference.build_projection(sources, ROOT)
        self.assertEqual(projected["youtube"]["subscriber_count"], 123000)
        self.assertNotIn("youtube", projected["candidate_signals"] if "candidate_signals" in projected else {})
        metrics = reference.derive_hud_metrics(sources)
        for lang in ("fr", "en"):
            with_youtube = reference.render_html(projected, metrics, lang=lang, signal_histories=histories)
            without = copy.deepcopy(projected)
            without.pop("youtube")
            without_html = reference.render_html(without, metrics, lang=lang, signal_histories=histories)
            self.assertNotEqual(with_youtube, without_html)
            self.assertEqual(with_youtube.count(b'data-provider="'), 3)
            card = with_youtube.split(b'data-provider="youtube"', 1)[1].split(b'</article>', 1)[0]
            self.assertIn(("123\u202f000" if lang == "fr" else "123,000").encode(), card)
            self.assertIn(projected["youtube"]["channel_url"].encode(), card)
            unavailable = without_html.split(b'data-provider="youtube"', 1)[1].split(b'</article>', 1)[0]
            self.assertNotIn(b'href=', unavailable)

    def test_workflow_contract_and_publication_time_fallback(self):
        workflow = (ROOT / ".github/workflows/publish-candidate-family.yml").read_text(encoding="utf-8")
        start = workflow.index("- name: Collect candidate YouTube evidence")
        end = workflow.index("- name: Build and validate candidate publication")
        step = workflow[start:end]
        self.assertIn("${{ secrets.YOUTUBE_API_KEY }}", step)
        self.assertEqual(workflow.count("${{ secrets.YOUTUBE_API_KEY }}"), 1)
        self.assertIn("github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'", step)
        pre = workflow.index("- name: Check offline provider contracts before collection")
        self.assertLess(pre, start)
        self.assertNotIn("-m unittest", step)
        self.assertIn("steps.youtube.outputs.published_at || steps.polymarket.outputs.published_at", workflow)
        self.assertIn('if [[ -z "$publication_time" ]]; then', workflow)
        self.assertIn('["published_at"]', workflow[end:])
        self.assertNotIn("continue-on-error", step)
        self.assertNotIn("YOUTUBE_API_KEY", step[step.index("run: |") :])
        self.assertGreaterEqual(workflow.count("candidate_youtube.json publication_manifest.json"), 5)

    def test_pr_validation_offline(self):
        workflow = (ROOT / ".github/workflows/validate-dashboard.yml").read_text(encoding="utf-8")
        self.assertIn("test_candidate_youtube", workflow)
        self.assertNotIn("build_candidate_youtube.py", workflow)
        self.assertNotIn("YOUTUBE_API_KEY", workflow)

    def test_no_runtime_search_or_browser_fetch(self):
        self.assertEqual(set(builder.PARTS), {"channels", "playlistItems", "videos"})
        self.assertNotIn("forHandle", (ROOT / "build_candidate_youtube.py").read_text(encoding="utf-8"))


class YouTubeTransportTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"YOUTUBE_API_KEY": SECRET})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @staticmethod
    def response(raw):
        response = io.BytesIO(raw)
        response.status = 200
        return response

    def assert_transport_failure(self, error, attempts=1):
        opener, sleep = Mock(side_effect=error), Mock()
        client = builder.YouTubeClient(opener=opener, sleep=sleep)
        captured_out, captured_err = io.StringIO(), io.StringIO()
        with redirect_stdout(captured_out), redirect_stderr(captured_err):
            try:
                client.get("channels", id=A)
            except contract.CandidateYouTubeError:
                rendered = traceback.format_exc()
            else:
                self.fail("expected collection error")
        self.assertNotIn(SECRET, rendered + captured_out.getvalue() + captured_err.getvalue())
        self.assertEqual(opener.call_count, attempts)
        self.assertEqual(sleep.call_count, attempts - 1)

    def test_request_parts_fields_and_timeout(self):
        opener = Mock(return_value=self.response(b'{"items": []}'))
        client = builder.YouTubeClient(opener=opener)
        client.get("channels", id=A, maxResults=50)
        request = opener.call_args.args[0]
        parsed = urlsplit(request.full_url)
        self.assertEqual(parsed.scheme + "://" + parsed.netloc + parsed.path, builder.API_ROOT + "channels")
        params = parse_qs(parsed.query)
        self.assertEqual(params["part"], ["snippet,contentDetails,statistics"])
        self.assertNotIn("description", params["fields"][0])
        self.assertEqual(opener.call_args.kwargs, {"timeout": 20})

    def test_malformed_json(self):
        for raw in (b"not json", b"\xff", b"null", b"[]", b'{}', b'{"error": {"message": "bad"}}'):
            with self.subTest(raw=raw), self.assertRaises(contract.CandidateYouTubeError):
                builder.YouTubeClient(opener=Mock(return_value=self.response(raw))).get("channels", id=A)

    def test_response_size_bound(self):
        with self.assertRaises(contract.CandidateYouTubeError):
            builder.YouTubeClient(opener=Mock(return_value=self.response(b" " * (builder.MAX_BYTES + 1)))).get("channels")

    def test_http_400(self): self.assert_transport_failure(HTTPError("https://example.test/?key=" + SECRET, 400, SECRET, {}, None))
    def test_http_401(self): self.assert_transport_failure(HTTPError("https://example.test/?key=" + SECRET, 401, SECRET, {}, None))
    def test_http_403(self): self.assert_transport_failure(HTTPError("https://example.test/?key=" + SECRET, 403, SECRET, {}, None))
    def test_quota_error(self): self.assert_transport_failure(HTTPError("https://example.test/?key=" + SECRET, 403, "quotaExceeded " + SECRET, {}, None))
    def test_http_429(self): self.assert_transport_failure(HTTPError("https://example.test/?key=" + SECRET, 429, SECRET, {}, None), 3)
    def test_retryable_5xx(self):
        for code in (500, 502, 503, 504):
            with self.subTest(code=code): self.assert_transport_failure(HTTPError("https://example.test/?key=" + SECRET, code, SECRET, {}, None), 3)
    def test_timeout(self): self.assert_transport_failure(TimeoutError(SECRET), 3)
    def test_network_failure(self): self.assert_transport_failure(URLError(SECRET), 3)

    def test_retry_recovers_and_retry_after_capped(self):
        opener = Mock(side_effect=[HTTPError("secret " + SECRET, 429, SECRET, {"Retry-After": "900"}, None), self.response(b'{"items": []}')])
        sleep = Mock()
        self.assertEqual(builder.YouTubeClient(opener=opener, sleep=sleep).get("channels"), {"items": []})
        sleep.assert_called_once_with(30)

    def test_missing_key(self):
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": ""}), self.assertRaises(contract.CandidateYouTubeError): builder.YouTubeClient()

    def test_secret_response_not_stored_or_logged(self):
        opener = Mock(return_value=self.response(json.dumps({"items": [], "message": SECRET}).encode()))
        try:
            builder.YouTubeClient(opener=opener).get("channels")
        except contract.CandidateYouTubeError:
            self.assertNotIn(SECRET, traceback.format_exc())
        else:
            self.fail("expected credential contamination failure")

    def test_secret_absent_from_artifact_and_projection(self):
        payload = fixture_payload()
        client = builder.YouTubeClient(opener=Mock())
        client.assert_secret_absent(payload)
        client.assert_secret_absent(contract.candidate_projection(payload, "marine-le-pen"))
        self.assertNotIn(SECRET, json.dumps(payload))

    def test_failed_collection_preserves_prior_valid_artifact(self):
        registry = json.loads((ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8"))
        ids = {r["candidate_id"] for r in registry["candidates"]}
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            output, mapping_path = root / "snapshot.json", root / "mapping.json"
            previous = json.dumps(fixture_payload(ids)).encode()
            output.write_bytes(previous)
            mapping_path.write_text(json.dumps(fixture_mapping()), encoding="utf-8")
            bad_clients = [builder.YouTubeClient(opener=Mock(side_effect=URLError(SECRET)), sleep=Mock()), FixtureClient({**fixture(), "channels": {"items": []}})]
            for client in bad_clients:
                with self.assertRaises(contract.CandidateYouTubeError):
                    builder.collect(output, mapping_path=mapping_path, registry_path=ROOT / "candidate_candidacy_status.json", client=client, observed_at=OBSERVED)
                self.assertEqual(output.read_bytes(), previous)
                self.assertEqual(list(root.glob("*.tmp")), [])

    def test_cli_failure_logs_are_generic(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(builder, "collect", side_effect=OSError(SECRET)), patch("sys.argv", ["collector"]), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(builder.main(), 1)
        self.assertNotIn(SECRET, out.getvalue() + err.getvalue())


class TaskOnePreservationTests(unittest.TestCase):
    # LF-normalized baseline hashes also work in GitHub's Linux checkout.
    HASHES = {
        "candidate_polymarket.py": "e7396dbde85efd34f3e0bf3ee81da3104991ddce7e3a8f49b8670f7606e0ed51",
        "build_candidate_polymarket.py": "cbadf171faa42fd582414417b61665c8db1d62611b931889bf2df602e1b890a3",
        "polymarket_candidate_markets.json": "8842f38c2115a3e5ad7de4dbf622f90e56ff4100526e97b718e94c56c092eec8",
        "docs/candidate-polymarket.md": "ada260d174dc0a55edb92cf7e1273136e6cd1f80fd871e6afefef89aeebdc883",
        "assets/candidate-page.js": "219efa69fecc5974af541c00cb36d817b2bf7fcb7177eb70e58893775eea6262",
    }

    def test_protected_files_unchanged(self):
        for path, expected in self.HASHES.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest(), expected)

    def test_original_candidate_css_before_public_signals_unchanged(self):
        css = (ROOT / "assets/candidate-page.css").read_bytes().replace(b"\r\n", b"\n")
        original = css.split(b"/* Public sources reuse candidate panels", 1)[0]
        import subprocess
        committed = subprocess.check_output(["git", "show", "HEAD:assets/candidate-page.css"], cwd=ROOT)
        self.assertEqual(original, committed.replace(b"\r\n", b"\n").split(b"/* Public sources reuse candidate panels", 1)[0])

    def test_representative_polymarket_values_and_html(self):
        import build_candidate_reference as reference
        payload = json.loads((ROOT / "candidate_polymarket.json").read_text(encoding="utf-8"))
        by_id = {r["candidate_id"]: r for r in payload["candidates"]}
        # Scheduled Polymarket observations legitimately change. Exact Task-1
        # artifact bytes/values are audited separately during this implementation.
        for cid in ("marine-le-pen", "edouard-philippe", "gabriel-attal", "raphael-glucksmann"):
            if by_id[cid]["status"] == "observed":
                self.assertIsInstance(by_id[cid]["implied_probability"], (int, float))
            else:
                self.assertIsNone(by_id[cid]["implied_probability"])
            row = {**by_id[cid], "observed_at": payload["observed_at"], "stale_after_hours": 48}
            for lang, prefix in (("fr", ""), ("en", "en/")):
                html = (ROOT / f"{prefix}candidates/{cid}/index.html").read_text(encoding="utf-8")
                self.assertIn(reference.render_polymarket({"candidate_id": cid, "polymarket": row}, lang,
                    reference.load_signal_histories(ROOT)), html)


if __name__ == "__main__":
    unittest.main()
