"""Synthetic offline assertions shared by the three provider-specific test suites."""
import copy
import importlib
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock
from candidate_history import HistoryError, instant, iso, encode

ROOT = Path(__file__).resolve().parent


class HistoryCases:
    def setUp(self):
        self.mod = importlib.import_module("candidate_" + self.provider + "_history")
        self.builder = importlib.import_module("build_candidate_" + self.provider + "_history")
        self.validate = getattr(self.mod, "validate_candidate_" + self.provider + "_history")
        self.snapshot = json.loads((ROOT / ("candidate_" + self.provider + ".json")).read_text(encoding="utf-8"))
        self.mapping = json.loads((ROOT / self.mapping_file).read_text(encoding="utf-8"))
        self.ids = {r["candidate_id"] for r in self.snapshot["candidates"]}
        # Synthetic numeric accounts keep the tests independent of live availability/counts.
        configs = self.mapping[{"polymarket": "markets", "youtube": "channels", "bluesky": "accounts"}[self.provider]][:2]
        for config in configs:
            row = next(r for r in self.snapshot["candidates"] if r["candidate_id"] == config["candidate_id"])
            row["status"] = "observed"
            if self.provider == "youtube":
                channel = config["channel_id"]
                row.update(channel_id=channel, channel_title="Synthetic channel", channel_url="https://www.youtube.com/channel/"+channel,
                           subscriber_count=123000, hidden_subscriber_count=False, channel_view_count=100000,
                           public_video_count=0, uploads_playlist_id="UU"+channel[2:], latest_upload_at=None,
                           uploads_last_7d=0, recent_window_complete=True, recent_video_metrics_complete=True, recent_videos=[])
            elif self.provider == "bluesky":
                row.update(did=config["did"], handle="synthetic.bsky.social", display_name="Synthetic account",
                           profile_url="https://bsky.app/profile/"+config["did"], followers_count=12345, follows_count=10, posts_count=10)
            else:
                from candidate_polymarket import SOURCE_URL
                row.update(**{key:config[key] for key in ("market_id","market_slug","outcome_id","outcome_name")},
                           source_url=SOURCE_URL+"/"+config["market_slug"], implied_probability=0.3)
        self.history = self.mod.build_history(self.snapshot, self.mapping, self.ids)
        observed = next(r for r in self.snapshot["candidates"] if r["status"] == "observed")
        self.cid = observed["candidate_id"]
        self.row = next(r for r in self.history["candidates"] if r["candidate_id"] == self.cid)
        self.anchor = instant(self.snapshot["observed_at"])

    def build(self, previous=None):
        return self.mod.build_history(self.snapshot, self.mapping, self.ids, previous)

    def advance(self, days=0, seconds=0):
        stamp = iso(self.anchor + timedelta(days=days, seconds=seconds))
        self.snapshot.update(observed_at=stamp, generated_at=stamp)
        if self.provider == "youtube":
            for row in self.snapshot["candidates"]:
                if row["status"] == "observed":
                    row.update(recent_window_complete=False, uploads_last_7d=None, latest_upload_at=None,
                               recent_videos=[], recent_video_metrics_complete=True)

    def point(self, offset, value):
        result = {"observed_at": iso(self.anchor + timedelta(days=offset)), self.metric: value}
        if self.provider == "polymarket": result["source"] = "clob_prices_history"
        return result

    def update(self, directory):
        output = Path(directory) / "history.json"
        snapshot = Path(directory) / "snapshot.json"
        snapshot.write_bytes(encode(self.snapshot))
        kwargs = dict(snapshot_path=snapshot, mapping_path=ROOT / self.mapping_file,
                      registry_path=ROOT / "candidate_candidacy_status.json")
        call = self.builder.collect if self.provider == "polymarket" else self.builder.update
        return output, lambda: call(output, **kwargs)

    def test_seed_exact_current_observation_and_registry_coverage(self):
        self.validate(self.history, mapping=self.mapping, candidate_ids=self.ids, snapshot=self.snapshot)
        self.assertEqual(len(self.history["candidates"]), len(self.ids))
        self.assertEqual(self.row["points"][-1]["observed_at"], self.snapshot["observed_at"])
        self.assertEqual(self.build(self.history), self.history)
        self.assertEqual(encode(self.build()), encode(self.history))

    def test_schema_and_registry_mismatch(self):
        for change in ({"schema_version": "9"}, {"retention_days": 0}, {"extra": 1}):
            bad = copy.deepcopy(self.history); bad.update(change)
            with self.assertRaises(ValueError): self.validate(bad)
        with self.assertRaises(ValueError): self.validate(self.history, candidate_ids=self.ids - {self.cid})

    def test_duplicate_and_unordered_candidates(self):
        bad = copy.deepcopy(self.history); bad["candidates"].append(copy.deepcopy(bad["candidates"][0]))
        with self.assertRaises(ValueError): self.validate(bad)
        bad = copy.deepcopy(self.history); bad["candidates"].reverse()
        with self.assertRaises(ValueError): self.validate(bad)

    def test_duplicate_identity(self):
        bad = copy.deepcopy(self.history)
        rows = [r for r in bad["candidates"] if r[self.identity] is not None]
        for key in (["market_id", "yes_token_id"] if self.provider == "polymarket" else [self.identity]):
            rows[1][key] = rows[0][key]
        with self.assertRaises(ValueError): self.validate(bad)

    def test_identity_lock_and_mapping_mismatch(self):
        self.row[self.identity] = self.changed_identity
        with self.assertRaises(ValueError): self.validate(self.history, mapping=self.mapping)
        with self.assertRaises(ValueError): self.build(self.history)

    def test_malformed_timestamps(self):
        for value in ("2026-10-17", "2026-99-99T00:00:00Z", "2026-10-17T00:00:00+01:00", None):
            bad = copy.deepcopy(self.history); bad["observed_at"] = value
            with self.assertRaises(ValueError): self.validate(bad)
            bad = copy.deepcopy(self.history)
            next(r for r in bad["candidates"] if r["points"])["points"][0]["observed_at"] = value
            with self.assertRaises(ValueError): self.validate(bad)

    def test_malformed_numbers(self):
        for value in (-1, True, "12", None, float("nan"), float("inf"), 2**53):
            bad = copy.deepcopy(self.history)
            next(r for r in bad["candidates"] if r["points"])["points"][0][self.metric] = value
            with self.assertRaises(ValueError): self.validate(bad)

    def test_unmapped_never_has_a_fake_zero(self):
        row = next(r for r in self.history["candidates"] if r[self.identity] is None)
        self.assertEqual(row["points"], [])
        row["points"] = [self.point(0, 0)]
        with self.assertRaises(ValueError): self.validate(self.history)

    def test_same_day_latest_successful_observation(self):
        self.advance(seconds=1)
        updated = self.build(self.history)
        row = next(r for r in updated["candidates"] if r["candidate_id"] == self.cid)
        self.assertEqual(len(row["points"]), 1)
        self.assertEqual(row["points"][0]["observed_at"], self.snapshot["observed_at"])

    def test_conflicting_same_timestamp_and_backwards_snapshot_fail_closed(self):
        self.row["points"][0][self.metric] = 0.123456 if self.provider == "polymarket" else 123456
        with self.assertRaises(ValueError): self.build(self.history)
        self.advance(seconds=-1)
        with self.assertRaises(ValueError): self.build(self.history)

    def test_retention_and_future_append(self):
        self.row["points"].insert(0, self.point(-89, 0.1 if self.provider == "polymarket" else 100))
        self.advance(days=1)
        result = self.build(self.history)
        row = next(r for r in result["candidates"] if r["candidate_id"] == self.cid)
        self.assertEqual(len(row["points"]), 2)
        self.assertEqual(row["points"][0]["observed_at"], iso(self.anchor))

    def test_duplicate_daily_points_rejected(self):
        self.row["points"].append(copy.deepcopy(self.row["points"][0]))
        with self.assertRaises(ValueError): self.validate(self.history)

    def test_null_and_exact_seven_day_delta(self):
        self.assertIsNone(self.mod.derive_delta({"points": []}, 7))
        self.assertIsNone(self.mod.derive_delta(self.row, 7))
        values = (0.421, 0.459) if self.provider == "polymarket" else (100, 125)
        row = {"points": [self.point(-7, values[0]), self.point(0, values[1])]}
        self.assertEqual(self.mod.derive_delta(row, 7), 3.8 if self.provider == "polymarket" else 25)
        self.assertIsNone(self.mod.derive_delta(row, 30))

    def test_irregular_seven_and_thirty_day_anchors(self):
        values = (0.1, 0.2, 0.4) if self.provider == "polymarket" else (100, 200, 400)
        for days in (7, 30):
            row = {"points": [self.point(-days-1, values[0]), self.point(-days+1, values[1]), self.point(0, values[2])]}
            self.assertEqual(self.mod.derive_delta(row, days), 30.0 if self.provider == "polymarket" else 300)

    def test_failed_validation_preserves_prior_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output, call = self.update(directory); output.write_bytes(encode(self.history)); before = output.read_bytes()
            self.snapshot["observed_at"] = "invalid"
            _, call = self.update(directory)
            with self.assertRaises(ValueError): call()
            self.assertEqual(output.read_bytes(), before)

    def test_atomic_replace_failure_preserves_prior_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output, call = self.update(directory); output.write_bytes(encode(self.history)); before = output.read_bytes()
            with mock.patch("build_candidate_signals.os.replace", side_effect=OSError("injected replace failure")):
                with self.assertRaises(OSError): call()
            self.assertEqual(output.read_bytes(), before)
            self.assertFalse(list(Path(directory).glob(".history.json.*.tmp")))

    def test_offline_append_and_check_make_no_api_call(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output, call = self.update(directory)
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("unexpected API call")):
                call()
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), self.history)

    def test_new_registry_candidates_start_empty_without_losing_existing_history(self):
        row = copy.deepcopy(next(r for r in self.snapshot["candidates"] if r["status"] in
            ("unavailable_no_market", "unavailable_no_channel", "unavailable_no_account")))
        row["candidate_id"] = "zz-history-test-candidate"
        self.ids.add(row["candidate_id"])
        self.snapshot["candidates"].append(row)
        result = self.build(self.history)
        self.assertEqual(len(result["candidates"]), len(self.ids))
        self.assertEqual(result["candidates"][-1]["points"], [])
        self.assertEqual(next(r for r in result["candidates"] if r["candidate_id"] == self.cid)["points"],self.row["points"])
