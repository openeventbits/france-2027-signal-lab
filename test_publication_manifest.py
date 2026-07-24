import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import build_publication_manifest as manifest_builder


ROOT = Path(__file__).resolve().parent
PUBLISHED_AT = "2026-07-24T10:00:00Z"


def write_json(root, name, payload):
    (root / name).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def complete_inputs(root):
    write_json(
        root,
        "polls.json",
        [
            {"fieldwork_end": "2026-07-09"},
            {"fieldwork_end": "2026-07-10"},
        ],
    )
    write_json(
        root,
        "second_round_polls.json",
        {
            "schema_version": "1.0",
            "generated_at": "2026-07-22T17:01:45Z",
            "events": [
                {"fieldwork_end": "2026-07-07"},
                {"fieldwork_end": "2026-07-08"},
            ],
        },
    )
    write_json(
        root,
        "closest_tested_runoff.json",
        {
            "schema_version": "1.0",
            "generated_at": "2026-07-22T17:01:45Z",
            "status": "agree",
        },
    )
    write_json(
        root,
        "news_wire.json",
        {
            "schema_version": 1,
            "generated_at": "2026-07-24T08:03:00Z",
            "discovery": {
                "approved_publisher_domains": 202,
            },
            "feed_coverage": {
                "configured_media_publishers": 180,
                "configured_feeds": 209,
                "feeds_due_this_run": 53,
                "feeds_successful_this_run": 52,
                "contributing_publishers_30d": 86,
            },
            "election_news": [
                {
                    "publisher": "Publisher A",
                    "published_at": "2026-07-24T06:00:00Z",
                },
                {
                    "publisher": "Publisher B",
                    "published_at": "2026-07-24T06:04:00Z",
                },
            ],
            "notable_developments": [],
            "relevant_news": [],
            "candidate_watch": [],
        },
    )
    write_json(
        root,
        "claims_under_scrutiny.json",
        {
            "schema_version": 1,
            "generated_at": "2026-07-17T12:00:19Z",
            "reviews": [
                {"review_date": "2026-07-16"},
                {"review_date": "2026-07-17"},
            ],
        },
    )
    write_json(
        root,
        "recent_changes.json",
        {
            "schema_version": 1,
            "generated_at": "2026-07-24T08:04:00Z",
            "last_successful_check_at": "2026-07-24T08:04:00Z",
            "items": [
                {"trusted_change_at": "2026-07-22T11:11:10Z"},
                {"trusted_change_at": "2026-07-21"},
            ],
        },
    )


class PublicationManifestTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / f".publication-manifest-test-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        complete_inputs(self.root)

    def build(self, published_at=PUBLISHED_AT):
        return manifest_builder.build_manifest(
            self.root,
            published_at=published_at,
        )

    def test_deterministic_snapshot_id(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertRegex(first["snapshot_id"], r"^[0-9a-f]{64}$")

    def test_snapshot_id_is_independent_of_published_at(self):
        first = self.build("2026-07-24T10:00:00Z")
        second = self.build("2026-07-24T11:00:00Z")
        self.assertNotEqual(first["published_at"], second["published_at"])
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])

    def test_valid_complete_inputs(self):
        manifest = self.build()
        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["published_at"], PUBLISHED_AT)
        self.assertEqual(
            set(manifest["lanes"]),
            {"polls", "runoff", "news", "claims", "recent_changes"},
        )
        self.assertEqual(manifest["warnings"], [])
        for lane in manifest["lanes"].values():
            self.assertTrue(lane["available"])
            self.assertTrue(lane["valid"])
            self.assertRegex(lane["sha256"], r"^[0-9a-f]{64}$")

    def test_missing_lane_completes_with_warning(self):
        (self.root / "news_wire.json").unlink()
        manifest = self.build()
        lane = manifest["lanes"]["news"]
        self.assertFalse(lane["available"])
        self.assertFalse(lane["valid"])
        self.assertIsNone(lane["sha256"])
        self.assertEqual(lane["timestamp_status"], "missing")
        self.assertIn("news_wire.json is missing", lane["warnings"])
        self.assertIn("news_wire.json is missing", manifest["warnings"])

    def test_malformed_lane_completes_with_warning(self):
        (self.root / "claims_under_scrutiny.json").write_text(
            "{not json",
            encoding="utf-8",
        )
        manifest = self.build()
        lane = manifest["lanes"]["claims"]
        self.assertTrue(lane["available"])
        self.assertFalse(lane["valid"])
        self.assertRegex(lane["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(lane["timestamp_status"], "invalid")
        self.assertTrue(
            any("malformed JSON" in warning for warning in lane["warnings"])
        )

    def test_poll_timestamp_is_unknown(self):
        lane = self.build()["lanes"]["polls"]
        self.assertEqual(lane["timestamp_status"], "unknown")
        self.assertNotIn("generated_at", lane)
        self.assertNotIn("last_success_at", lane)

    def test_no_cross_lane_timestamp_inference(self):
        manifest = self.build()
        recent_check = manifest["lanes"]["recent_changes"]["last_success_at"]
        self.assertEqual(recent_check, "2026-07-24T08:04:00Z")
        self.assertNotIn(recent_check, manifest["lanes"]["polls"].values())
        self.assertEqual(
            manifest["lanes"]["polls"]["timestamp_status"],
            "unknown",
        )

    def test_poll_data_as_of_uses_latest_valid_fieldwork_end(self):
        self.assertEqual(
            self.build()["lanes"]["polls"]["data_as_of"],
            "2026-07-10",
        )

    def test_runoff_data_as_of_uses_latest_valid_fieldwork_end(self):
        self.assertEqual(
            self.build()["lanes"]["runoff"]["data_as_of"],
            "2026-07-08",
        )

    def test_claim_data_as_of_uses_latest_valid_review_date(self):
        self.assertEqual(
            self.build()["lanes"]["claims"]["data_as_of"],
            "2026-07-17",
        )

    def test_source_network_metrics_remain_separate(self):
        network = self.build()["source_network"]
        self.assertEqual(
            network,
            {
                "approved_publisher_domains": 202,
                "configured_media_publishers": 180,
                "configured_routes_or_feeds": 209,
                "routes_due_in_run": 53,
                "successful_due_routes": 52,
                "contributing_publishers_in_retained_period": 86,
                "publishers_represented_in_accepted_election_news": 2,
            },
        )

    def test_atomic_output_replaces_the_target_only_at_the_end(self):
        target = self.root / manifest_builder.OUTPUT_NAME
        target.write_text("last good", encoding="utf-8")
        payload = self.build()

        with patch.object(
            manifest_builder.os,
            "replace",
            side_effect=OSError("simulated replace failure"),
        ):
            with self.assertRaises(OSError):
                manifest_builder.atomic_write_json(target, payload)

        self.assertEqual(target.read_text(encoding="utf-8"), "last good")
        self.assertEqual(
            list(self.root.glob(f".{manifest_builder.OUTPUT_NAME}.*.tmp")),
            [],
        )

        manifest_builder.atomic_write_json(target, payload)
        written = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(written["snapshot_id"], payload["snapshot_id"])

    def test_check_does_not_modify_publication_manifest(self):
        target = self.root / manifest_builder.OUTPUT_NAME
        original = '{"sentinel": true}\n'
        target.write_text(original, encoding="utf-8")

        with patch.object(Path, "cwd", return_value=self.root):
            exit_code = manifest_builder.main(
                ["--check", "--published-at", PUBLISHED_AT]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_content_change_changes_snapshot_id(self):
        first = self.build()["snapshot_id"]
        polls = json.loads((self.root / "polls.json").read_text(encoding="utf-8"))
        polls.append({"fieldwork_end": "2026-07-11"})
        write_json(self.root, "polls.json", polls)
        self.assertNotEqual(first, self.build()["snapshot_id"])


if __name__ == "__main__":
    unittest.main()
