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
from rn_agenda_adapter import RnAgendaAdapterError


ROOT = Path(__file__).resolve().parent
GENERATED_AT = "2026-08-01T12:34:56Z"


def rn_event(
    observed_at=GENERATED_AT,
    *,
    event_key="rn-agenda-marine-le-pen-2026-08-27-1645-debate",
    title="Marine Le Pen sur LCI",
    scheduled_start="2026-08-27T16:45:00+02:00",
):
    return {
        "event_key": event_key,
        "event_id": campaign_event_id("campaign_events", event_key),
        "event_type": "debate",
        "title": title,
        "candidate_ids": ["marine-le-pen"],
        "candidate_names": ["Marine Le Pen"],
        "scheduled_start": scheduled_start,
        "time_precision": "datetime",
        "timezone": "Europe/Paris",
        "organization": "MEDEF",
        "status": "scheduled",
        "status_as_of": observed_at[:10],
        "evidence_status": "verified",
        "last_verified_at": observed_at,
        "evidence": [
            {
                "source_id": "rn-agenda",
                "source_url": "https://rassemblementnational.fr/agenda",
                "source_publisher": "Rassemblement National",
                "source_type": "party_first_party",
                "evidence_type": "explicit_schedule",
            }
        ],
    }

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
            "source_event_builders": {"rn-agenda": lambda **_kwargs: []},
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

    def production_registry(self):
        return json.loads(
            (ROOT / "campaign_event_sources.json").read_text(encoding="utf-8")
        )

    def registry_with_rn(self, **changes):
        payload = self.production_registry()
        source = next(
            item for item in payload["sources"] if item["source_id"] == "rn-agenda"
        )
        source.update(changes)
        return self.write_json("changed-sources.json", payload)

    def assert_two_milestones(self, artifact):
        self.assertEqual(
            [
                event["event_type"]
                for event in artifact["institutional_milestones"]
            ],
            ["first_round", "second_round"],
        )
    def assert_last_good(self, action):
        sentinel = b'{"last_good":true}\n'
        self.output.write_bytes(sentinel)
        with self.assertRaises(builder.BuildCampaignEventsError):
            action()
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assertEqual(list(self.temporary_root.glob(".campaign_events.json.*.tmp")), [])

    def test_production_adapter_map_is_exact(self):
        self.assertEqual(set(builder._PRODUCTION_SOURCE_EVENT_BUILDERS), {"rn-agenda"})
        self.assertEqual(
            builder._PRODUCTION_SOURCE_EVENT_BUILDERS["rn-agenda"].__name__,
            "build_rn_agenda_events",
        )

    def test_exact_one_event_rn_success_invokes_injected_builder_once(self):
        source_builder = mock.Mock(return_value=[rn_event()])
        artifact = self.build(
            source_event_builders={"rn-agenda": source_builder}
        )

        source_builder.assert_called_once_with(observed_at=GENERATED_AT)
        self.assertEqual(len(artifact["campaign_events"]), 1)
        self.assertEqual(
            artifact["campaign_events"][0]["event_key"],
            "rn-agenda-marine-le-pen-2026-08-27-1645-debate",
        )
        self.assertEqual(
            artifact["campaign_events"][0]["event_id"],
            "ce-de75c4df4e8c72a7cc486f26",
        )
        self.assertEqual(artifact["data_as_of"], GENERATED_AT)
        self.assert_two_milestones(artifact)
        validate_campaign_events_artifact(artifact)

    def test_valid_zero_removes_previous_rn_partition(self):
        self.build(
            generated_at="2026-08-01T16:00:00Z",
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [
                    rn_event("2026-08-01T16:00:00Z")
                ]
            },
        )
        artifact = self.build(
            generated_at="2026-08-02T16:00:00Z",
            preserve_generated_at_from=self.output,
            source_event_builders={"rn-agenda": lambda **_kwargs: []},
        )

        self.assertEqual(artifact["campaign_events"], [])
        self.assert_two_milestones(artifact)
        self.assertEqual(artifact["data_as_of"], "2026-08-01T00:00:00Z")

    def test_successful_replacement_removes_missing_prior_rn_event(self):
        older = "2026-08-01T16:00:00Z"
        first = rn_event(older)
        missing = rn_event(
            older,
            event_key="rn-agenda-marine-le-pen-2027-01-15-1930-debate",
            title="Marine Le Pen en débat en janvier",
            scheduled_start="2027-01-15T19:30:00+01:00",
        )
        self.build(
            generated_at=older,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [first, missing]
            },
        )
        artifact = self.build(
            generated_at="2026-08-02T16:00:00Z",
            preserve_generated_at_from=self.output,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [
                    rn_event("2026-08-02T16:00:00Z")
                ]
            },
        )

        self.assertEqual(
            [event["event_key"] for event in artifact["campaign_events"]],
            [first["event_key"]],
        )
        self.assert_two_milestones(artifact)

    def test_optional_transport_failure_preserves_previous_rn_partition(self):
        observed = "2026-08-01T16:00:00Z"
        previous = self.build(
            generated_at=observed,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [rn_event(observed)]
            },
        )
        previous_bytes = self.output.read_bytes()
        source_builder = mock.Mock(side_effect=OSError("offline"))
        with mock.patch("builtins.print") as printer:
            artifact = self.build(
                generated_at="2026-08-02T16:00:00Z",
                preserve_generated_at_from=self.output,
                source_event_builders={"rn-agenda": source_builder},
            )

        self.assertEqual(artifact, previous)
        self.assertEqual(self.output.read_bytes(), previous_bytes)
        self.assertEqual(
            artifact["campaign_events"][0]["last_verified_at"], observed
        )
        printer.assert_called_once_with(
            "warning: Campaign Events source rn-agenda failed; "
            "preserved 1 previous record"
        )
        self.assert_two_milestones(artifact)

    def test_optional_parser_failure_preserves_previous_rn_partition(self):
        observed = "2026-08-01T16:00:00Z"
        previous = self.build(
            generated_at=observed,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [rn_event(observed)]
            },
        )
        source_builder = mock.Mock(
            side_effect=RnAgendaAdapterError("unrecognized structure")
        )
        with mock.patch("builtins.print"):
            artifact = self.build(
                generated_at="2026-08-02T16:00:00Z",
                preserve_generated_at_from=self.output,
                source_event_builders={"rn-agenda": source_builder},
            )
        self.assertEqual(artifact, previous)
        self.assert_two_milestones(artifact)

    def test_required_source_failure_aborts_and_preserves_output(self):
        required_registry = self.registry_with_rn(required=True)
        source_builder = mock.Mock(side_effect=OSError("offline"))
        self.assert_last_good(
            lambda: self.build(
                source_registry_path=required_registry,
                source_event_builders={"rn-agenda": source_builder},
            )
        )
        source_builder.assert_called_once_with(observed_at=GENERATED_AT)

    def test_invalid_previous_artifact_is_not_trusted_for_optional_failure(self):
        invalid_previous = self.temporary_root / "invalid-previous.json"
        invalid_previous.write_text("{not json", encoding="utf-8")
        with mock.patch("builtins.print") as printer:
            artifact = self.build(
                generated_at="2026-08-02T16:00:00Z",
                preserve_generated_at_from=invalid_previous,
                source_event_builders={
                    "rn-agenda": mock.Mock(side_effect=OSError("offline"))
                },
            )
        self.assertEqual(artifact["campaign_events"], [])
        self.assertEqual(artifact["generated_at"], "2026-08-02T16:00:00Z")
        printer.assert_called_once_with(
            "warning: Campaign Events source rn-agenda failed; "
            "preserved 0 previous records"
        )
        self.assert_two_milestones(artifact)

    def test_disallowed_zero_uses_optional_last_good_semantics(self):
        registry_path = self.registry_with_rn(zero_result_valid=False)
        observed = "2026-08-01T16:00:00Z"
        previous = self.build(
            generated_at=observed,
            source_registry_path=registry_path,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [rn_event(observed)]
            },
        )
        previous_bytes = self.output.read_bytes()
        with mock.patch("builtins.print") as printer:
            artifact = self.build(
                generated_at="2026-08-02T16:00:00Z",
                source_registry_path=registry_path,
                preserve_generated_at_from=self.output,
                source_event_builders={"rn-agenda": lambda **_kwargs: []},
            )
        self.assertEqual(artifact, previous)
        self.assertEqual(self.output.read_bytes(), previous_bytes)
        printer.assert_called_once_with(
            "warning: Campaign Events source rn-agenda returned zero events "
            "while zero_result_valid is false; preserved 1 previous record"
        )
        self.assert_two_milestones(artifact)

    def test_identical_source_duplicates_collapse_deterministically(self):
        event = rn_event()
        artifact = self.build(
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [event, json.loads(json.dumps(event))]
            }
        )
        self.assertEqual(len(artifact["campaign_events"]), 1)
        self.assert_two_milestones(artifact)

    def test_conflicting_event_key_fails_without_replacing_output(self):
        first = rn_event()
        conflict = rn_event(title="Conflicting title")
        self.assert_last_good(
            lambda: self.build(
                source_event_builders={
                    "rn-agenda": lambda **_kwargs: [first, conflict]
                }
            )
        )

    def test_conflicting_event_id_fails_without_replacing_output(self):
        first = rn_event()
        conflict = rn_event(
            event_key="rn-agenda-marine-le-pen-2027-01-15-1930-debate",
            scheduled_start="2027-01-15T19:30:00+01:00",
        )
        conflict["event_id"] = first["event_id"]
        self.assert_last_good(
            lambda: self.build(
                source_event_builders={
                    "rn-agenda": lambda **_kwargs: [first, conflict]
                }
            )
        )

    def test_unchanged_source_preserves_nested_timestamps_and_exact_bytes(self):
        previous_observed = "2026-08-01T16:00:00Z"
        previous = self.build(
            generated_at=previous_observed,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [rn_event(previous_observed)]
            },
        )
        previous_bytes = self.output.read_bytes()
        current_observed = "2026-08-02T16:00:00Z"
        current = self.build(
            generated_at=current_observed,
            preserve_generated_at_from=self.output,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [rn_event(current_observed)]
            },
        )

        self.assertEqual(current, previous)
        self.assertEqual(self.output.read_bytes(), previous_bytes)
        self.assertEqual(current["generated_at"], previous_observed)
        self.assertEqual(
            current["campaign_events"][0]["status_as_of"], "2026-08-01"
        )
        self.assertEqual(
            current["campaign_events"][0]["last_verified_at"], previous_observed
        )

    def test_substantive_source_change_uses_current_observation_fields(self):
        previous_observed = "2026-08-01T16:00:00Z"
        self.build(
            generated_at=previous_observed,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [rn_event(previous_observed)]
            },
        )
        current_observed = "2026-08-02T16:00:00Z"
        artifact = self.build(
            generated_at=current_observed,
            preserve_generated_at_from=self.output,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [
                    rn_event(current_observed, title="Marine Le Pen face au MEDEF")
                ]
            },
        )

        event = artifact["campaign_events"][0]
        self.assertEqual(artifact["generated_at"], current_observed)
        self.assertEqual(artifact["data_as_of"], current_observed)
        self.assertEqual(event["status_as_of"], "2026-08-02")
        self.assertEqual(event["last_verified_at"], current_observed)
        self.assert_two_milestones(artifact)

    def test_invalid_adapter_output_does_not_replace_last_good(self):
        observed = "2026-08-01T16:00:00Z"
        self.build(
            generated_at=observed,
            source_event_builders={
                "rn-agenda": lambda **_kwargs: [rn_event(observed)]
            },
        )
        previous_bytes = self.output.read_bytes()
        invalid = rn_event("2026-08-02T16:00:00Z")
        invalid["evidence"][0]["source_publisher"] = "Wrong Publisher"
        with self.assertRaises(builder.BuildCampaignEventsError):
            self.build(
                generated_at="2026-08-02T16:00:00Z",
                preserve_generated_at_from=self.output,
                source_event_builders={"rn-agenda": lambda **_kwargs: [invalid]},
            )
        self.assertEqual(self.output.read_bytes(), previous_bytes)
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
