import copy
import json
import socket
import unittest
from pathlib import Path
from unittest import mock

from campaign_event_sources import (
    CAMPAIGN_EVENT_TYPES,
    INSTITUTIONAL_EVENT_TYPES,
    CampaignEventSourceRegistryError,
    load_campaign_event_source_registry,
    normalize_campaign_event_source_registry,
    validate_campaign_event_source_registry,
)


ROOT = Path(__file__).resolve().parent


def source_record(
    source_id="official-calendar",
    url="https://events.example.org/calendar",
    **changes,
):
    source = {
        "source_id": source_id,
        "publisher": "Official Publisher",
        "source_type": "official_structured",
        "url": url,
        "allowed_lanes": ["campaign_events"],
        "allowed_event_types": ["rally"],
        "enabled": True,
        "required": False,
        "refresh_class": "daily",
        "zero_result_valid": True,
    }
    source.update(changes)
    return source


def registry(*sources):
    return {"schema_version": "1.0", "sources": list(sources)}


class CampaignEventSourceRegistryTests(unittest.TestCase):
    def assert_invalid(self, payload, pattern=None):
        context = self.assertRaises(CampaignEventSourceRegistryError)
        with context:
            validate_campaign_event_source_registry(payload)
        if pattern is not None:
            self.assertRegex(str(context.exception), pattern)

    def test_production_registry_has_exact_approved_institutional_sources(self):
        loaded = load_campaign_event_source_registry(
            ROOT / "campaign_event_sources.json"
        )
        self.assertEqual(
            [source["source_id"] for source in loaded["sources"]],
            [
                "interieur-presidential-calendar",
                "vie-publique-presidential-calendar",
            ],
        )
        self.assertEqual(
            loaded["sources"],
            [
                {
                    "source_id": "interieur-presidential-calendar",
                    "publisher": "Ministère de l’Intérieur",
                    "source_type": "official_unstructured",
                    "url": "https://www.elections.interieur.gouv.fr/scrutins/lelection-presidentielle",
                    "allowed_lanes": ["institutional_milestones"],
                    "allowed_event_types": ["first_round", "second_round"],
                    "enabled": True,
                    "required": True,
                    "refresh_class": "manual",
                    "zero_result_valid": False,
                },
                {
                    "source_id": "vie-publique-presidential-calendar",
                    "publisher": "Vie publique",
                    "source_type": "official_unstructured",
                    "url": "https://www.vie-publique.fr/en-bref/303896-election-presidentielle-2027-les-dates-sont-connues",
                    "allowed_lanes": ["institutional_milestones"],
                    "allowed_event_types": ["first_round", "second_round"],
                    "enabled": True,
                    "required": True,
                    "refresh_class": "manual",
                    "zero_result_valid": False,
                },
            ],
        )

    def test_valid_empty_registry_remains_supported_in_memory(self):
        expected = {"schema_version": "1.0", "sources": []}
        validate_campaign_event_source_registry(expected)
        self.assertEqual(normalize_campaign_event_source_registry(expected), expected)

    def test_exact_top_level_keys(self):
        for changed in (
            {"sources": []},
            {"schema_version": "1.0"},
            {"schema_version": "1.0", "sources": [], "extra": True},
        ):
            with self.subTest(changed=changed):
                self.assert_invalid(changed, "exact allowed keys")

    def test_schema_version_and_sources_type(self):
        self.assert_invalid(
            {"schema_version": "2.0", "sources": []},
            "exactly '1.0'",
        )
        self.assert_invalid(
            {"schema_version": "1.0", "sources": {}},
            "sources must be a list",
        )

    def test_malformed_json_is_wrapped(self):
        target = ROOT / "malformed-campaign-event-sources.json"
        with mock.patch.object(Path, "read_text", return_value="{not-json"):
            with self.assertRaisesRegex(
                CampaignEventSourceRegistryError,
                "malformed JSON",
            ):
                load_campaign_event_source_registry(target)

    def test_exact_source_keys_and_prohibited_fields(self):
        base = source_record()
        missing = copy.deepcopy(base)
        missing.pop("publisher")
        self.assert_invalid(registry(missing), "missing")
        for field in (
            "confidence",
            "probability",
            "ranking",
            "inference",
            "llm_rationale",
        ):
            changed = copy.deepcopy(base)
            changed[field] = "not allowed"
            with self.subTest(field=field):
                self.assert_invalid(registry(changed), "unexpected")

    def test_source_order_is_normalized_and_canonical_order_is_enforced(self):
        later = source_record(
            "z-source",
            "https://z.example.org/events",
        )
        earlier = source_record(
            "a-source",
            "https://a.example.org/events",
        )
        unordered = registry(later, earlier)
        normalized = normalize_campaign_event_source_registry(unordered)
        self.assertEqual(
            [item["source_id"] for item in normalized["sources"]],
            ["a-source", "z-source"],
        )
        self.assert_invalid(unordered, "deterministic source ordering")
        validate_campaign_event_source_registry(normalized)

    def test_source_id_must_be_lowercase_ascii_kebab_case(self):
        for identifier in (
            "Uppercase",
            "under_score",
            "accent-é",
            "leading-",
            "-trailing",
            "two--hyphens",
        ):
            with self.subTest(identifier=identifier):
                self.assert_invalid(
                    registry(source_record(source_id=identifier)),
                    "lowercase ASCII kebab-case",
                )

    def test_duplicate_source_ids_are_rejected(self):
        self.assert_invalid(
            registry(
                source_record("same-source", "https://one.example.org/events"),
                source_record("same-source", "https://two.example.org/events"),
            ),
            "duplicate source_id",
        )

    def test_duplicate_urls_are_rejected_after_normalization(self):
        self.assert_invalid(
            registry(
                source_record("source-a", "https://events.example.org/list"),
                source_record("source-b", "HTTPS://EVENTS.EXAMPLE.ORG/list"),
            ),
            "duplicate source URL",
        )

    def test_urls_must_be_absolute_https(self):
        for url in (
            "http://events.example.org/list",
            "//events.example.org/list",
            "/events/list",
            "https:///events/list",
        ):
            with self.subTest(url=url):
                self.assert_invalid(registry(source_record(url=url)), "HTTPS")

    def test_hostname_validation_and_normalization(self):
        for url in (
            "https://localhost/events",
            "https://bad_host.example.org/events",
            "https://-bad.example.org/events",
            "https://example.org./events",
            "https://user@example.org/events",
            "https://example.org:443/events",
        ):
            with self.subTest(url=url):
                self.assert_invalid(registry(source_record(url=url)))
        changed = registry(source_record(url="HTTPS://EVENTS.EXAMPLE.ORG/list"))
        normalized = normalize_campaign_event_source_registry(changed)
        self.assertEqual(
            normalized["sources"][0]["url"],
            "https://events.example.org/list",
        )

    def test_source_type_vocabulary(self):
        self.assert_invalid(
            registry(source_record(source_type="social_media")),
            "source_type is not allowed",
        )

    def test_lane_vocabulary_and_unique_nonempty_lists(self):
        for lanes in ([], ["news_stories"], ["campaign_events"] * 2):
            with self.subTest(lanes=lanes):
                self.assert_invalid(
                    registry(source_record(allowed_lanes=lanes)),
                    "allowed_lanes",
                )

    def test_event_type_vocabulary_and_lane_compatibility(self):
        validate_campaign_event_source_registry(
            registry(source_record(allowed_event_types=["debate"]))
        )
        self.assert_invalid(
            registry(
                source_record(
                    allowed_lanes=["campaign_events"],
                    allowed_event_types=["first_round"],
                )
            ),
            "cover exactly",
        )
        both = registry(
            source_record(
                allowed_lanes=[
                    "institutional_milestones",
                    "campaign_events",
                ],
                allowed_event_types=["first_round", "rally"],
            )
        )
        normalized = normalize_campaign_event_source_registry(both)
        self.assertEqual(
            normalized["sources"][0]["allowed_lanes"],
            ["campaign_events", "institutional_milestones"],
        )
        self.assertEqual(
            normalized["sources"][0]["allowed_event_types"],
            ["rally", "first_round"],
        )

    def test_event_type_vocabularies_add_only_debate(self):
        self.assertEqual(
            CAMPAIGN_EVENT_TYPES,
            {
                "rally",
                "public_meeting",
                "debate",
                "candidate_visit",
                "campaign_launch",
            },
        )
        self.assertEqual(
            INSTITUTIONAL_EVENT_TYPES,
            {
                "sponsorship_deadline",
                "official_candidate_list",
                "campaign_period_boundary",
                "first_round",
                "second_round",
            },
        )

    def test_event_type_order_is_campaign_then_unchanged_institutional(self):
        payload = registry(
            source_record(
                allowed_lanes=[
                    "institutional_milestones",
                    "campaign_events",
                ],
                allowed_event_types=[
                    "second_round",
                    "campaign_launch",
                    "candidate_visit",
                    "first_round",
                    "debate",
                    "public_meeting",
                    "rally",
                    "campaign_period_boundary",
                    "official_candidate_list",
                    "sponsorship_deadline",
                ],
            )
        )
        normalized = normalize_campaign_event_source_registry(payload)
        self.assertEqual(
            normalized["sources"][0]["allowed_event_types"],
            [
                "rally",
                "public_meeting",
                "debate",
                "candidate_visit",
                "campaign_launch",
                "sponsorship_deadline",
                "official_candidate_list",
                "campaign_period_boundary",
                "first_round",
                "second_round",
            ],
        )

    def test_boolean_fields_require_actual_booleans(self):
        for field in ("enabled", "required", "zero_result_valid"):
            for bad_value in (0, 1, "true", None):
                changed = source_record(**{field: bad_value})
                with self.subTest(field=field, value=bad_value):
                    self.assert_invalid(registry(changed), "actual boolean")

    def test_refresh_class_is_controlled(self):
        for refresh_class in (
            "hourly",
            "every_3_hours",
            "every_12_hours",
            "daily",
            "manual",
        ):
            validate_campaign_event_source_registry(
                registry(source_record(refresh_class=refresh_class))
            )
        self.assert_invalid(
            registry(source_record(refresh_class="whenever")),
            "refresh_class is not allowed",
        )

    def test_candidate_first_party_ownership_is_explicit(self):
        missing = source_record(source_type="candidate_first_party")
        self.assert_invalid(registry(missing), "requires candidate_ids")
        valid = source_record(
            source_type="candidate_first_party",
            candidate_ids=["bruno-retailleau"],
        )
        validate_campaign_event_source_registry(registry(valid))
        invalid_organization = copy.deepcopy(valid)
        invalid_organization["organization"] = "Party"
        self.assert_invalid(
            registry(invalid_organization),
            "must not set organization",
        )

    def test_party_and_organizer_ownership_is_explicit(self):
        for source_type in ("party_first_party", "organizer_first_party"):
            with self.subTest(source_type=source_type):
                self.assert_invalid(
                    registry(source_record(source_type=source_type)),
                    "requires organization",
                )
                validate_campaign_event_source_registry(
                    registry(
                        source_record(
                            source_type=source_type,
                            organization="Organization",
                        )
                    )
                )
        self.assert_invalid(
            registry(source_record(organization="Irrelevant Owner")),
            "ownership fields are not relevant",
        )

    def test_candidate_ids_must_be_canonical_and_unique(self):
        base = {
            "source_type": "candidate_first_party",
            "candidate_ids": ["not-in-registry"],
        }
        self.assert_invalid(
            registry(source_record(**base)),
            "not a canonical candidate ID",
        )
        base["candidate_ids"] = ["bruno-retailleau", "bruno-retailleau"]
        self.assert_invalid(
            registry(source_record(**base)),
            "duplicate candidate IDs",
        )

    def test_normalization_is_deterministic_and_does_not_mutate(self):
        payload = registry(
            source_record(
                source_type="candidate_first_party",
                candidate_ids=["david-lisnard", "bruno-retailleau"],
            )
        )
        original = copy.deepcopy(payload)
        first = normalize_campaign_event_source_registry(payload)
        second = normalize_campaign_event_source_registry(payload)
        self.assertEqual(first, second)
        self.assertEqual(payload, original)
        self.assertEqual(
            first["sources"][0]["candidate_ids"],
            ["bruno-retailleau", "david-lisnard"],
        )

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
            loaded = load_campaign_event_source_registry(
                ROOT / "campaign_event_sources.json"
            )
        self.assertEqual(
            [source["source_id"] for source in loaded["sources"]],
            [
                "interieur-presidential-calendar",
                "vie-publique-presidential-calendar",
            ],
        )


if __name__ == "__main__":
    unittest.main()
