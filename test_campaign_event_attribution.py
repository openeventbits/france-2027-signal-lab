"""Tests for deterministic pre-observation candidate attribution."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import importlib
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

import campaign_event_attribution
from campaign_event_attribution import (
    AttributedStructuredEvent,
    CandidateAttributionBatch,
    CandidateAttributionConfigurationError,
    attribute_structured_event,
    attribute_structured_events,
)
from campaign_event_structured import StructuredEventRecord


ROOT = Path(__file__).resolve().parent
EXPLICIT_SOURCE = {
    "source_id": "structured-party-agenda",
    "source_type": "party_first_party",
    "collection": {"attribution_policy": "explicit_participant"},
}
MULTI_SOURCE = {
    "source_id": "structured-debate-agenda",
    "source_type": "organizer_first_party",
    "collection": {"attribution_policy": "multi_candidate_explicit"},
}


def structured_event(
    title: str,
    *,
    description: str | None = None,
    organization: str | None = None,
    event_url: str | None = None,
) -> StructuredEventRecord:
    return StructuredEventRecord(
        title=title,
        scheduled_start="2026-08-29T19:00:00+02:00",
        time_precision="datetime",
        timezone="Europe/Paris",
        source_format="json_ld",
        description=description,
        organization=organization,
        event_url=event_url,
    )


def source(
    policy: str,
    *,
    source_type: str = "party_first_party",
    candidate_ids: list[str] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "source_id": "test-source",
        "source_type": source_type,
        "collection": {"attribution_policy": policy},
    }
    if candidate_ids is not None:
        result["candidate_ids"] = candidate_ids
    return result


class CampaignEventAttributionTests(unittest.TestCase):
    def attribute(
        self,
        event: StructuredEventRecord,
        supplied_source: dict[str, object] = EXPLICIT_SOURCE,
    ) -> AttributedStructuredEvent | None:
        return attribute_structured_event(
            event,
            source=supplied_source,
            candidate_registry_path=ROOT / "candidate_candidacy_status.json",
        )

    def assert_candidate_ids(
        self,
        event: StructuredEventRecord,
        expected: tuple[str, ...],
        supplied_source: dict[str, object] = EXPLICIT_SOURCE,
    ) -> AttributedStructuredEvent:
        attributed = self.attribute(event, supplied_source)
        self.assertIsNotNone(attributed)
        assert attributed is not None
        self.assertEqual(attributed.candidate_ids, expected)
        return attributed

    def test_plain_name_mentions_do_not_attribute(self):
        for title in (
            "Mobilisation pour Marine Le Pen",
            "Les propositions de Jean-Luc Mélenchon",
            "Discussion sur la candidature de Gabriel Attal",
            "Portrait politique d'Édouard Philippe",
        ):
            with self.subTest(title=title):
                self.assertIsNone(self.attribute(structured_event(title)))

    def test_exact_full_canonical_name_relation_attributes(self):
        attributed = self.assert_candidate_ids(
            structured_event("Meeting avec Édouard Philippe"),
            ("edouard-philippe",),
        )
        self.assertEqual(attributed.candidate_names, ("Édouard Philippe",))
        self.assertEqual(attributed.attribution_basis, "explicit_participant")

    def test_case_accent_and_hyphen_normalization_are_deterministic(self):
        cases = (
            ("Meeting avec EDOUARD PHILIPPE", "edouard-philippe"),
            ("Meeting avec Jean Luc Melenchon", "jean-luc-melenchon"),
        )
        for title, candidate_id in cases:
            with self.subTest(title=title):
                self.assert_candidate_ids(
                    structured_event(title),
                    (candidate_id,),
                )

    def test_surname_partial_and_longer_tokens_do_not_match(self):
        for title in (
            "Meeting avec Philippe",
            "Meeting avec Jean-Luc",
            "Meeting avec Jean-Luc Mélenchoniste",
            "Meeting avec Attaliste",
        ):
            with self.subTest(title=title):
                self.assertIsNone(self.attribute(structured_event(title)))

    def test_bounded_prefix_relationships_attribute(self):
        for title in (
            "Meeting avec David Lisnard",
            "En présence de David Lisnard",
            "Discours de David Lisnard",
            "Intervention de David Lisnard",
            "Prise de parole de David Lisnard",
            "Réunion publique avec David Lisnard",
            "Débat avec David Lisnard",
        ):
            with self.subTest(title=title):
                self.assert_candidate_ids(
                    structured_event(title),
                    ("david-lisnard",),
                )

    def test_bounded_candidate_participation_verbs_attribute(self):
        for title in (
            "David Lisnard participera",
            "David Lisnard participe",
            "David Lisnard interviendra",
            "David Lisnard intervient",
            "David Lisnard sera présent",
            "David Lisnard sera présente",
            "David Lisnard prendra la parole",
            "David Lisnard débattra",
        ):
            with self.subTest(title=title):
                self.assert_candidate_ids(
                    structured_event(title),
                    ("david-lisnard",),
                )

    def test_lisnard_discours_de_rentree_is_attributed(self):
        self.assert_candidate_ids(
            structured_event("Discours de rentrée de David Lisnard"),
            ("david-lisnard",),
        )

    def test_discours_aboutness_does_not_imply_participation(self):
        for title in (
            "Discussion sur le discours de rentrée de David Lisnard",
            "Analyse du discours de campagne de David Lisnard",
            "Débat sur le discours de rentrée de David Lisnard",
        ):
            with self.subTest(title=title):
                self.assertIsNone(self.attribute(structured_event(title)))

    def test_generic_nouvelle_energie_event_and_leadership_are_not_inferred(self):
        event = structured_event(
            "Réunion départementale Nouvelle Énergie",
            description="Rencontre des adhérents du mouvement.",
            organization="Nouvelle Énergie",
        )
        self.assertIsNone(self.attribute(event))

    def test_melenchon_campaign_launch_explicit_description_attributes(self):
        event = structured_event(
            "Meeting national de lancement de la campagne présidentielle",
            description="Un meeting avec Jean-Luc Mélenchon à Saint-Denis.",
            organization="La France insoumise",
        )
        self.assert_candidate_ids(event, ("jean-luc-melenchon",))

    def test_amfis_without_candidate_relation_is_rejected(self):
        event = structured_event(
            "AMFIS 2026",
            description="Université d'été ouverte au public.",
            organization="La France insoumise",
        )
        self.assertIsNone(self.attribute(event))

    def test_support_retransmission_projection_and_watch_party_are_rejected(self):
        for title in (
            "Réunion de soutien à Bruno Retailleau",
            "Comité de soutien avec Marine Le Pen",
            "Soirée de soutien à Édouard Philippe",
            "Retransmission du débat avec Bruno Retailleau",
            "Projection du débat avec Bruno Retailleau",
            "Watch party du débat avec Bruno Retailleau",
        ):
            with self.subTest(title=title):
                self.assertIsNone(self.attribute(structured_event(title)))

    def test_exact_candidate_organization_is_an_explicit_role(self):
        self.assert_candidate_ids(
            structured_event("Rencontre publique", organization="David Lisnard"),
            ("david-lisnard",),
        )

    def test_url_slug_is_not_candidate_evidence(self):
        event = structured_event(
            "Rencontre publique",
            event_url="https://example.test/avec-david-lisnard",
        )
        self.assertIsNone(self.attribute(event))

    def test_paired_debate_forms_attribute_both_candidates(self):
        for title in (
            "François Hollande face à Édouard Philippe",
            "François Hollande contre Édouard Philippe",
            "François Hollande vs Édouard Philippe",
            "Débat entre François Hollande et Édouard Philippe",
        ):
            with self.subTest(title=title):
                attributed = self.assert_candidate_ids(
                    structured_event(title),
                    ("francois-hollande", "edouard-philippe"),
                    MULTI_SOURCE,
                )
                self.assertEqual(
                    attributed.candidate_names,
                    ("François Hollande", "Édouard Philippe"),
                )

    def test_multi_candidate_policy_rejects_only_one_explicit_candidate(self):
        self.assertIsNone(
            self.attribute(
                structured_event("Débat avec Édouard Philippe"),
                MULTI_SOURCE,
            )
        )

    def test_candidate_owned_campaign_uses_canonical_owner_without_mention(self):
        owned_source = source(
            "candidate_owned_campaign",
            source_type="candidate_first_party",
            candidate_ids=["gabriel-attal"],
        )
        attributed = self.assert_candidate_ids(
            structured_event("Réunion de campagne"),
            ("gabriel-attal",),
            owned_source,
        )
        self.assertEqual(attributed.candidate_names, ("Gabriel Attal",))
        self.assertEqual(
            attributed.attribution_basis,
            "candidate_owned_campaign",
        )

    def test_candidate_owned_campaign_is_not_an_attendance_claim(self):
        owned_source = source(
            "candidate_owned_campaign",
            source_type="candidate_first_party",
            candidate_ids=["gabriel-attal"],
        )
        attributed = self.assert_candidate_ids(
            structured_event("Comité local de soutien"),
            ("gabriel-attal",),
            owned_source,
        )
        self.assertNotEqual(attributed.attribution_basis, "explicit_participant")

    def test_candidate_owned_campaign_configuration_defects_fail_closed(self):
        cases = (
            source(
                "candidate_owned_campaign",
                source_type="candidate_first_party",
            ),
            source(
                "candidate_owned_campaign",
                source_type="party_first_party",
                candidate_ids=["gabriel-attal"],
            ),
            source(
                "candidate_owned_campaign",
                source_type="candidate_first_party",
                candidate_ids=["not-canonical"],
            ),
            source(
                "candidate_owned_campaign",
                source_type="candidate_first_party",
                candidate_ids=["sarah-knafo"],
            ),
        )
        for supplied_source in cases:
            with self.subTest(source=supplied_source):
                with self.assertRaises(CandidateAttributionConfigurationError):
                    self.attribute(
                        structured_event("Réunion de campagne"),
                        supplied_source,
                    )

    def test_custom_and_unknown_policies_fail_as_configuration_errors(self):
        for policy in ("custom", "not-a-policy"):
            with self.subTest(policy=policy):
                with self.assertRaises(CandidateAttributionConfigurationError):
                    self.attribute(structured_event("Meeting"), source(policy))

    def test_current_hidden_candidates_are_not_in_active_matching_universe(self):
        for title in (
            "Meeting avec Sarah Knafo",
            "Meeting avec Sébastien Lecornu",
        ):
            with self.subTest(title=title):
                self.assertIsNone(self.attribute(structured_event(title)))
        self.assert_candidate_ids(
            structured_event("Meeting avec Bruno Retailleau"),
            ("bruno-retailleau",),
        )

    def test_batch_counts_normal_rejections_and_preserves_accepted_record(self):
        accepted_event = structured_event("Meeting avec David Lisnard")
        batch = attribute_structured_events(
            (
                structured_event("AMFIS 2026"),
                accepted_event,
                structured_event("Réunion départementale Nouvelle Énergie"),
            ),
            source=EXPLICIT_SOURCE,
            candidate_registry_path=ROOT / "candidate_candidacy_status.json",
        )
        self.assertEqual(batch.rejected_records, 2)
        self.assertEqual(len(batch.accepted), 1)
        self.assertIs(batch.accepted[0].structured_event, accepted_event)

    def test_result_models_are_immutable_and_do_not_create_public_fields(self):
        attributed = self.assert_candidate_ids(
            structured_event("Meeting avec David Lisnard"),
            ("david-lisnard",),
        )
        batch = CandidateAttributionBatch(accepted=(attributed,), rejected_records=0)
        with self.assertRaises(FrozenInstanceError):
            attributed.attribution_basis = "candidate_owned_campaign"
        with self.assertRaises(FrozenInstanceError):
            batch.rejected_records = 1
        self.assertEqual(
            {field.name for field in fields(attributed)},
            {
                "structured_event",
                "candidate_ids",
                "candidate_names",
                "attribution_basis",
            },
        )
        self.assertTrue(
            {
                "event_type",
                "event_id",
                "event_key",
                "evidence",
                "status",
            }.isdisjoint({field.name for field in fields(attributed)})
        )

    def test_malformed_candidate_registry_fails_as_configuration_error(self):
        with self.assertRaises(CandidateAttributionConfigurationError):
            attribute_structured_event(
                structured_event("Meeting avec David Lisnard"),
                source=EXPLICIT_SOURCE,
                candidate_registry_path=ROOT / "missing-candidate-registry.json",
            )

    def test_repeated_calls_are_deterministic(self):
        event = structured_event("François Hollande face à Édouard Philippe")
        first = self.attribute(event, MULTI_SOURCE)
        second = self.attribute(event, MULTI_SOURCE)
        self.assertEqual(first, second)

    def test_attributor_performs_no_network_access(self):
        with (
            mock.patch("urllib.request.urlopen", side_effect=AssertionError),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError,
            ),
        ):
            self.assert_candidate_ids(
                structured_event("Meeting avec David Lisnard"),
                ("david-lisnard",),
            )

    def test_module_import_performs_no_network_access(self):
        module_name = "_campaign_event_attribution_import_test"
        module_path = Path(__file__).with_name("campaign_event_attribution.py")
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        imported = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = imported
        try:
            with (
                mock.patch("urllib.request.urlopen", side_effect=AssertionError),
                mock.patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError,
                ),
            ):
                spec.loader.exec_module(imported)
        finally:
            sys.modules.pop(module_name, None)
        self.assertTrue(hasattr(imported, "attribute_structured_events"))


if __name__ == "__main__":
    unittest.main()
