import copy
import json
import shutil
import socket
import unittest
import uuid
from pathlib import Path
from unittest import mock

from campaign_event_institutional_seeds import (
    CampaignEventInstitutionalSeedError,
    load_campaign_event_institutional_seeds,
    normalize_campaign_event_institutional_seeds,
    serialize_campaign_event_institutional_seeds,
    validate_campaign_event_institutional_seeds,
)


ROOT = Path(__file__).resolve().parent
SEEDS_PATH = ROOT / "campaign_event_institutional_seeds.json"
SOURCES_PATH = ROOT / "campaign_event_sources.json"


def production_payload():
    return json.loads(SEEDS_PATH.read_text(encoding="utf-8"))


class CampaignEventInstitutionalSeedTests(unittest.TestCase):
    def setUp(self):
        self.temporary_root = ROOT / f".campaign-event-seeds-test-{uuid.uuid4().hex}"
        self.temporary_root.mkdir()
        self.addCleanup(shutil.rmtree, self.temporary_root, True)

    def write_registry(self, payload):
        target = self.temporary_root / "sources.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target

    def assert_invalid(self, payload, pattern=None, registry=SOURCES_PATH):
        context = self.assertRaises(CampaignEventInstitutionalSeedError)
        with context:
            normalize_campaign_event_institutional_seeds(
                payload,
                source_registry_path=registry,
            )
        if pattern is not None:
            self.assertRegex(str(context.exception), pattern)

    def test_exact_production_seed_set(self):
        payload = load_campaign_event_institutional_seeds(SEEDS_PATH)
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(
            [seed["event_key"] for seed in payload["seeds"]],
            [
                "presidential-2027-first-round",
                "presidential-2027-second-round",
            ],
        )
        self.assertEqual(
            [seed["event_type"] for seed in payload["seeds"]],
            ["first_round", "second_round"],
        )
        self.assertEqual(
            [seed["scheduled_start"] for seed in payload["seeds"]],
            ["2027-04-18", "2027-05-02"],
        )
        for seed in payload["seeds"]:
            self.assertEqual(seed["lane"], "institutional_milestones")
            self.assertEqual(seed["time_precision"], "date")
            self.assertEqual(seed["timezone"], "Europe/Paris")
            self.assertEqual(seed["status"], "scheduled")
            self.assertEqual(seed["evidence_status"], "verified")
            self.assertNotIn("candidate_ids", seed)
            self.assertNotIn("candidate_names", seed)
            self.assertEqual(
                [record["source_id"] for record in seed["evidence"]],
                [
                    "interieur-presidential-calendar",
                    "vie-publique-presidential-calendar",
                ],
            )
            self.assertTrue(
                all(
                    record["source_type"] == "official_unstructured"
                    and record["evidence_type"] == "official_rule_derivation"
                    for record in seed["evidence"]
                )
            )

    def test_exact_top_level_seed_and_evidence_keys(self):
        payload = production_payload()
        changed = copy.deepcopy(payload)
        changed["unknown"] = True
        self.assert_invalid(changed, "unexpected")
        changed = copy.deepcopy(payload)
        changed["seeds"][0].pop("title")
        self.assert_invalid(changed, "missing")
        changed = copy.deepcopy(payload)
        changed["seeds"][0]["evidence"][0]["metadata"] = {}
        self.assert_invalid(changed, "unexpected")

    def test_missing_and_duplicate_rounds_are_rejected(self):
        payload = production_payload()
        missing = copy.deepcopy(payload)
        missing["seeds"] = missing["seeds"][:1]
        self.assert_invalid(missing, "exactly first_round and second_round")
        duplicate = copy.deepcopy(payload)
        duplicate["seeds"][1]["event_key"] = "another-first-round"
        duplicate["seeds"][1]["event_type"] = "first_round"
        self.assert_invalid(duplicate, "duplicate event_type")

    def test_duplicate_seed_key_is_rejected(self):
        payload = production_payload()
        payload["seeds"][1]["event_key"] = payload["seeds"][0]["event_key"]
        self.assert_invalid(payload, "duplicate seed event_key")

    def test_campaign_type_and_candidate_data_are_rejected(self):
        payload = production_payload()
        payload["seeds"][0]["event_type"] = "rally"
        self.assert_invalid(payload, "institutional round type")
        payload = production_payload()
        payload["seeds"][0]["candidate_ids"] = []
        self.assert_invalid(payload, "unexpected")

    def test_date_only_contract_rejects_datetime_and_midnight(self):
        for value in (
            "18-04-2027",
            "2027-04-18T10:00:00+02:00",
            "2027-04-18T00:00:00+02:00",
        ):
            payload = production_payload()
            payload["seeds"][0]["scheduled_start"] = value
            with self.subTest(value=value):
                self.assert_invalid(payload, "date-only")
        payload = production_payload()
        payload["seeds"][0]["time_precision"] = "datetime"
        self.assert_invalid(payload, "exactly 'date'")

    def test_source_registry_parity(self):
        mutations = (
            ("source_publisher", "Interior Ministry", "publisher"),
            ("source_type", "official_structured", "source_type"),
            (
                "source_url",
                "https://calendar.elections.interieur.gouv.fr/presidential",
                "registered source URL",
            ),
        )
        for field, value, pattern in mutations:
            payload = production_payload()
            payload["seeds"][0]["evidence"][0][field] = value
            with self.subTest(field=field):
                self.assert_invalid(payload, pattern)

    def test_evidence_urls_require_exact_registered_url_without_mutation(self):
        registry = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        registered_urls = {
            source["source_id"]: source["url"] for source in registry["sources"]
        }
        for source_id, registered_url in registered_urls.items():
            source_path = registered_url.split("/", 3)
            same_host_unrelated = "/".join(source_path[:3]) + "/unrelated-page"
            variants = (
                same_host_unrelated,
                registered_url + "?view=alternate",
                registered_url + "#dates",
                registered_url + "/",
                registered_url.replace("https://", "http://", 1),
                registered_url.replace("www.", "WWW.", 1),
            )
            for variant in variants:
                payload = production_payload()
                for seed in payload["seeds"]:
                    record = next(
                        evidence
                        for evidence in seed["evidence"]
                        if evidence["source_id"] == source_id
                    )
                    record["source_url"] = variant
                original = copy.deepcopy(payload)
                with self.subTest(source_id=source_id, variant=variant):
                    self.assert_invalid(payload, "source_url")
                    self.assertEqual(payload, original)

        payload = production_payload()
        original = copy.deepcopy(payload)
        normalized = normalize_campaign_event_institutional_seeds(payload)
        self.assertEqual(payload, original)
        for seed in normalized["seeds"]:
            self.assertEqual(
                {
                    evidence["source_id"]: evidence["source_url"]
                    for evidence in seed["evidence"]
                },
                registered_urls,
            )

    def test_unknown_and_unauthorized_sources_are_rejected(self):
        payload = production_payload()
        payload["seeds"][0]["evidence"][0]["source_id"] = "unknown-source"
        self.assert_invalid(payload, "not authorized")

        registry = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        registry["sources"][0]["allowed_event_types"] = ["first_round"]
        registry_path = self.write_registry(registry)
        self.assert_invalid(
            production_payload(),
            "not authorized for second_round",
            registry_path,
        )

    def test_disabled_source_is_rejected(self):
        registry = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        registry["sources"][0]["enabled"] = False
        registry_path = self.write_registry(registry)
        self.assert_invalid(production_payload(), "disabled", registry_path)

    def test_both_registered_sources_are_required_for_each_seed(self):
        payload = production_payload()
        payload["seeds"][0]["evidence"] = payload["seeds"][0]["evidence"][:1]
        self.assert_invalid(payload, "exactly the authorized official sources")

    def test_scoring_inference_llm_and_opaque_fields_are_rejected(self):
        for field in (
            "confidence",
            "score",
            "probability",
            "ranking",
            "inferred_date",
            "llm_rationale",
            "raw_page",
            "metadata",
        ):
            payload = production_payload()
            payload["seeds"][0][field] = "not allowed"
            with self.subTest(field=field):
                self.assert_invalid(payload, "unexpected")

    def test_normalization_sorts_without_mutating(self):
        payload = production_payload()
        payload["seeds"].reverse()
        for seed in payload["seeds"]:
            seed["evidence"].reverse()
        original = copy.deepcopy(payload)
        normalized = normalize_campaign_event_institutional_seeds(payload)
        self.assertEqual(payload, original)
        self.assertEqual(
            [seed["event_type"] for seed in normalized["seeds"]],
            ["first_round", "second_round"],
        )
        self.assertTrue(
            all(
                [record["source_id"] for record in seed["evidence"]]
                == sorted(record["source_id"] for record in seed["evidence"])
                for seed in normalized["seeds"]
            )
        )
        validate_campaign_event_institutional_seeds(normalized)

    def test_deterministic_utf8_serialization(self):
        payload = production_payload()
        first = serialize_campaign_event_institutional_seeds(payload)
        second = serialize_campaign_event_institutional_seeds(copy.deepcopy(payload))
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertIn("Ministère".encode("utf-8"), first)
        self.assertNotIn(b"\\u00e8", first)

    def test_loading_performs_no_network_access(self):
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network access attempted"),
        ), mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network access attempted"),
        ):
            loaded = load_campaign_event_institutional_seeds(SEEDS_PATH)
        self.assertEqual(len(loaded["seeds"]), 2)


if __name__ == "__main__":
    unittest.main()
