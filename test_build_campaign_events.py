import json
import shutil
import socket
import unittest
import uuid
from pathlib import Path
from unittest import mock

import build_campaign_events as builder
from campaign_event_institutional_seeds import (
    load_campaign_event_institutional_seeds,
)
from campaign_events_contract import (
    campaign_event_id,
    validate_campaign_events_artifact,
)


ROOT = Path(__file__).resolve().parent
GENERATED_AT = "2026-08-01T12:34:56Z"


class BuildCampaignEventsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_root = ROOT / f".campaign-events-build-test-{uuid.uuid4().hex}"
        self.temporary_root.mkdir()
        self.addCleanup(shutil.rmtree, self.temporary_root, True)
        self.output = self.temporary_root / "campaign_events.json"

    def build(self, **changes):
        arguments = {
            "generated_at": GENERATED_AT,
            "seed_path": ROOT / "campaign_event_institutional_seeds.json",
            "source_registry_path": ROOT / "campaign_event_sources.json",
            "candidate_registry_path": ROOT / "candidate_candidacy_status.json",
            "output_path": self.output,
        }
        arguments.update(changes)
        return builder.build_from_paths(**arguments)

    def write_json(self, name, payload):
        target = self.temporary_root / name
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target

    def production_seeds(self):
        return json.loads(
            (ROOT / "campaign_event_institutional_seeds.json").read_text(
                encoding="utf-8"
            )
        )

    def assert_last_good(self, action):
        sentinel = b'{"last_good":true}\n'
        self.output.write_bytes(sentinel)
        with self.assertRaises(builder.BuildCampaignEventsError):
            action()
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assertEqual(list(self.temporary_root.glob(".campaign_events.json.*.tmp")), [])

    def test_successful_two_milestone_build(self):
        artifact = self.build()
        self.assertEqual(artifact["generated_at"], GENERATED_AT)
        self.assertEqual(artifact["data_as_of"], "2026-08-01T00:00:00Z")
        self.assertEqual(artifact["campaign_events"], [])
        self.assertEqual(len(artifact["institutional_milestones"]), 2)
        milestones = artifact["institutional_milestones"]
        self.assertEqual(
            [(item["event_type"], item["scheduled_start"]) for item in milestones],
            [("first_round", "2027-04-18"), ("second_round", "2027-05-02")],
        )
        for item in milestones:
            self.assertEqual(item["candidate_ids"], [])
            self.assertEqual(item["candidate_names"], [])
            self.assertEqual(item["time_precision"], "date")
            self.assertEqual(item["timezone"], "Europe/Paris")
            self.assertEqual(item["status"], "scheduled")
            self.assertEqual(item["evidence_status"], "verified")
        validate_campaign_events_artifact(
            artifact,
            source_registry_path=ROOT / "campaign_event_sources.json",
        )

    def test_stable_deterministic_ids_and_ordering(self):
        artifact = self.build()
        milestones = artifact["institutional_milestones"]
        self.assertEqual(
            [item["event_id"] for item in milestones],
            [
                campaign_event_id(
                    "institutional_milestones",
                    "presidential-2027-first-round",
                ),
                campaign_event_id(
                    "institutional_milestones",
                    "presidential-2027-second-round",
                ),
            ],
        )

    def test_exact_evidence_is_preserved_and_sorted(self):
        artifact = self.build()
        for item in artifact["institutional_milestones"]:
            self.assertEqual(
                [record["source_id"] for record in item["evidence"]],
                [
                    "interieur-presidential-calendar",
                    "vie-publique-presidential-calendar",
                ],
            )
            self.assertTrue(
                all(
                    record["evidence_type"] == "official_rule_derivation"
                    for record in item["evidence"]
                )
            )

    def test_repeated_build_is_byte_identical(self):
        self.build()
        first = self.output.read_bytes()
        self.build()
        self.assertEqual(self.output.read_bytes(), first)

    def test_valid_existing_artifact_prevents_requested_timestamp_churn(self):
        existing = self.build(generated_at="2026-08-01T16:00:00Z")
        existing_bytes = self.output.read_bytes()
        candidate_path = self.temporary_root / "candidate.json"
        candidate = self.build(
            generated_at="2026-08-02T16:00:00Z",
            output_path=candidate_path,
            preserve_generated_at_from=self.output,
        )
        self.assertEqual(candidate["generated_at"], existing["generated_at"])
        self.assertEqual(candidate, existing)
        self.assertEqual(candidate_path.read_bytes(), existing_bytes)
        self.assertEqual(
            [event["event_id"] for event in candidate["institutional_milestones"]],
            [event["event_id"] for event in existing["institutional_milestones"]],
        )

    def test_genuine_seed_change_uses_new_requested_timestamp(self):
        existing = self.build(generated_at="2026-08-01T16:00:00Z")
        existing_bytes = self.output.read_bytes()
        payload = self.production_seeds()
        payload["seeds"][0]["title"] += " — mise à jour"
        changed_seed_path = self.write_json("changed-seeds.json", payload)
        candidate_path = self.temporary_root / "changed-candidate.json"
        candidate = self.build(
            generated_at="2026-08-02T16:00:00Z",
            seed_path=changed_seed_path,
            output_path=candidate_path,
            preserve_generated_at_from=self.output,
        )
        self.assertEqual(candidate["generated_at"], "2026-08-02T16:00:00Z")
        self.assertNotEqual(candidate_path.read_bytes(), existing_bytes)
        self.assertNotEqual(candidate["institutional_milestones"], existing["institutional_milestones"])
        self.assertEqual(
            [event["event_id"] for event in candidate["institutional_milestones"]],
            [event["event_id"] for event in existing["institutional_milestones"]],
        )

    def test_invalid_existing_artifact_is_not_trusted(self):
        existing_path = self.temporary_root / "invalid-existing.json"
        existing_path.write_text("{not json", encoding="utf-8")
        candidate = self.build(
            generated_at="2026-08-02T16:00:00Z",
            preserve_generated_at_from=existing_path,
        )
        self.assertEqual(candidate["generated_at"], "2026-08-02T16:00:00Z")
        validate_campaign_events_artifact(
            candidate,
            source_registry_path=ROOT / "campaign_event_sources.json",
        )

    def test_tracked_artifact_regenerates_byte_for_byte_with_preservation(self):
        tracked = ROOT / "campaign_events.json"
        tracked_payload = json.loads(tracked.read_text(encoding="utf-8"))
        candidate = self.build(
            generated_at="2026-08-02T16:00:00Z",
            preserve_generated_at_from=tracked,
        )
        self.assertEqual(candidate["generated_at"], tracked_payload["generated_at"])
        self.assertEqual(self.output.read_bytes(), tracked.read_bytes())
        self.assertEqual(candidate, tracked_payload)

    def test_explicit_timestamp_is_required_and_local_timezone_independent(self):
        artifact = self.build(generated_at="2026-12-15T01:02:03Z")
        first_bytes = self.output.read_bytes()
        self.assertEqual(artifact["generated_at"], "2026-12-15T01:02:03Z")
        with mock.patch.dict("os.environ", {"TZ": "Pacific/Kiritimati"}):
            second = self.build(generated_at="2026-12-15T01:02:03Z")
        self.assertEqual(second, artifact)
        self.assertEqual(self.output.read_bytes(), first_bytes)

    def test_invalid_registry_preserves_last_good(self):
        invalid_registry = self.write_json(
            "invalid-sources.json",
            {"schema_version": "1.0", "sources": "invalid"},
        )
        self.assert_last_good(
            lambda: self.build(source_registry_path=invalid_registry)
        )

    def test_invalid_and_missing_seed_round_preserve_last_good(self):
        payload = self.production_seeds()
        payload["seeds"][0]["scheduled_start"] = "not-a-date"
        invalid_seeds = self.write_json("invalid-seeds.json", payload)
        self.assert_last_good(lambda: self.build(seed_path=invalid_seeds))

        payload = self.production_seeds()
        payload["seeds"] = payload["seeds"][:1]
        missing_round = self.write_json("missing-round.json", payload)
        self.assert_last_good(lambda: self.build(seed_path=missing_round))

    def test_missing_second_round_preserves_last_good(self):
        payload = self.production_seeds()
        payload["seeds"] = payload["seeds"][1:]
        missing_round = self.write_json("missing-first-round.json", payload)
        self.assert_last_good(lambda: self.build(seed_path=missing_round))

    def test_serialization_failure_preserves_last_good(self):
        self.assert_last_good(
            lambda: self._build_with_serialization_failure()
        )

    def _build_with_serialization_failure(self):
        with mock.patch.object(
            builder,
            "serialize_campaign_events",
            side_effect=RuntimeError("simulated serialization failure"),
        ):
            self.build()

    def test_atomic_promotion_failure_preserves_last_good_and_cleans_temp(self):
        sentinel = b"last good\n"
        self.output.write_bytes(sentinel)
        with mock.patch.object(
            builder.os,
            "replace",
            side_effect=OSError("simulated promotion failure"),
        ):
            with self.assertRaises(builder.BuildCampaignEventsError):
                self.build()
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assertEqual(list(self.temporary_root.glob(".campaign_events.json.*.tmp")), [])

    def test_bootstrap_empty_requires_explicit_option(self):
        artifact = self.build(
            seed_path=self.temporary_root / "missing.json",
            bootstrap_empty=True,
        )
        self.assertEqual(artifact["institutional_milestones"], [])
        self.assertEqual(artifact["data_as_of"], GENERATED_AT)
        with self.assertRaises(builder.BuildCampaignEventsError):
            self.build(seed_path=self.temporary_root / "missing.json")

    def test_no_network_access_or_unrelated_writes(self):
        before = {path.name for path in self.temporary_root.iterdir()}
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network access attempted"),
        ), mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network access attempted"),
        ):
            self.build()
        after = {path.name for path in self.temporary_root.iterdir()}
        self.assertEqual(after - before, {"campaign_events.json"})

    def test_cli_returns_nonzero_without_required_seed_file(self):
        exit_code = builder.main(
            [
                "--generated-at",
                GENERATED_AT,
                "--seeds",
                str(self.temporary_root / "missing.json"),
                "--output",
                str(self.output),
            ]
        )
        self.assertEqual(exit_code, 1)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
