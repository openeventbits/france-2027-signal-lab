import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from commission_notice_coverage import (
    CORROBORATING_WAVE_ATTRIBUTES,
    coverage_summary,
    coverage_warnings,
    reconcile_commission_notices,
    validate_notice_coverage,
)


def event(
    label,
    *,
    pollster="Ifop",
    start="2026-07-01",
    end="2026-07-02",
    source="https://example.test/poll",
    sample_size=1000,
    commissioner=None,
    publication_date=None,
    round_name="first_round",
    official_notice_id=None,
):
    payload = {
        "event_id": hashlib.sha256(label.encode()).hexdigest(),
        "round": round_name,
        "pollster": pollster,
        "fieldwork_start": start,
        "fieldwork_end": end,
        "source_url": source,
        "sample_size": sample_size,
        "commissioner": commissioner,
        "publication_date": publication_date,
    }
    if official_notice_id is not None:
        payload["official_notice_id"] = official_notice_id
    return payload


def notice(
    notice_id="commission:20000",
    *,
    classification="unsupported",
    pollster="Ifop",
    start="2026-07-01",
    end="2026-07-02",
    sample_size=None,
    commissioner=None,
    publication_date=None,
    confirmed_rounds=None,
):
    metadata = {
        "fieldwork_start": start,
        "fieldwork_end": end,
    }
    if sample_size is not None:
        metadata["sample_size"] = sample_size
    if commissioner is not None:
        metadata["commissioner"] = commissioner
    if publication_date is not None:
        metadata["publication_date"] = publication_date
    return {
        "notice_id": notice_id,
        "title": f"{notice_id} presidential voting intentions",
        "classification": classification,
        "institute": pollster,
        "confirmed_rounds": (
            ["first_round"]
            if confirmed_rounds is None
            else list(confirmed_rounds)
        ),
        "survey_metadata": metadata,
    }


def registry(*notices):
    return {"notices": list(notices)}


class CommissionNoticeCoverageTests(unittest.TestCase):
    def test_missing_legacy_coverage_is_unresolved_and_warns(self):
        item = notice()
        payload = registry(item)

        self.assertEqual(
            coverage_summary(payload),
            {
                "relevant": 1,
                "parsed": 0,
                "reconciled": 0,
                "unresolved": 1,
                "unresolved_notice_ids": [item["notice_id"]],
            },
        )
        self.assertEqual(len(coverage_warnings(payload)), 1)
        self.assertIn(item["notice_id"], coverage_warnings(payload)[0])
        self.assertNotIn("coverage", item)

    def test_parsed_requires_direct_official_notice_provenance(self):
        item = notice(classification="eligible")
        published = event(
            "parsed",
            official_notice_id=item["notice_id"],
        )

        reconcile_commission_notices(registry(item), [published])

        self.assertEqual(item["coverage"]["state"], "parsed")
        self.assertEqual(
            item["coverage"]["matched_event_ids"],
            [published["event_id"]],
        )

    def test_unsupported_notice_reconciles_to_exact_published_wave(self):
        item = notice()
        published = event("reconciled")
        payload = registry(item)

        reconcile_commission_notices(payload, [published])

        self.assertEqual(item["coverage"]["state"], "reconciled")
        self.assertEqual(coverage_warnings(payload), [])

    def test_unmatched_relevant_notice_is_unresolved_and_warns(self):
        item = notice()
        payload = registry(item)

        reconcile_commission_notices(payload, [])

        self.assertEqual(item["coverage"]["state"], "unresolved")
        self.assertEqual(len(coverage_warnings(payload)), 1)
        self.assertIn(item["notice_id"], coverage_warnings(payload)[0])

    def test_ambiguous_same_window_waves_remain_unresolved(self):
        item = notice()
        payload = registry(item)
        published = [
            event("wave-a", source="https://a.example/poll", sample_size=900),
            event("wave-b", source="https://b.example/poll", sample_size=1100),
        ]

        reconcile_commission_notices(payload, published)

        self.assertEqual(item["coverage"]["state"], "unresolved")
        self.assertEqual(
            item["coverage"]["method"],
            "ambiguous_published_waves",
        )

    def test_sample_size_can_disambiguate_same_window_waves(self):
        item = notice(sample_size=1100)
        matching = event(
            "wave-b",
            source="https://b.example/poll",
            sample_size=1100,
        )
        payload = registry(item)

        reconcile_commission_notices(
            payload,
            [
                event(
                    "wave-a",
                    source="https://a.example/poll",
                    sample_size=900,
                ),
                matching,
            ],
        )

        self.assertEqual(item["coverage"]["state"], "reconciled")
        self.assertEqual(
            item["coverage"]["matched_event_ids"],
            [matching["event_id"]],
        )

    def test_conflicting_corroboration_remains_unresolved(self):
        item = notice(sample_size=1000, commissioner="Y")
        payload = registry(item)
        published = [
            event(
                "wave-a",
                source="https://a.example/poll",
                sample_size=1000,
                commissioner="X",
            ),
            event(
                "wave-b",
                source="https://b.example/poll",
                sample_size=1200,
                commissioner="Y",
            ),
        ]

        reconcile_commission_notices(payload, published)

        self.assertEqual(item["coverage"]["state"], "unresolved")
        self.assertEqual(
            item["coverage"]["method"],
            "ambiguous_published_waves",
        )

    def test_conflicting_corroboration_is_attribute_order_independent(self):
        published = [
            event(
                "wave-a",
                source="https://a.example/poll",
                sample_size=1000,
                commissioner="X",
            ),
            event(
                "wave-b",
                source="https://b.example/poll",
                sample_size=1200,
                commissioner="Y",
            ),
        ]
        results = []
        orders = (
            CORROBORATING_WAVE_ATTRIBUTES,
            tuple(reversed(CORROBORATING_WAVE_ATTRIBUTES)),
        )
        for attribute_order in orders:
            item = notice(sample_size=1000, commissioner="Y")
            with patch(
                "commission_notice_coverage.CORROBORATING_WAVE_ATTRIBUTES",
                attribute_order,
            ):
                reconcile_commission_notices(registry(item), published)
            results.append(item["coverage"])

        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]["state"], "unresolved")
        self.assertEqual(
            results[0]["method"],
            "ambiguous_published_waves",
        )

    def test_unique_exact_wave_ignores_optional_metadata_mismatch(self):
        item = notice(sample_size=1200)
        published = event("unique-wave", sample_size=1000)

        reconcile_commission_notices(registry(item), [published])

        self.assertEqual(item["coverage"]["state"], "reconciled")
        self.assertEqual(
            item["coverage"]["matched_event_ids"],
            [published["event_id"]],
        )

    def test_reconciliation_persists_strict_coverage_for_all_relevant_notices(
        self,
    ):
        matched = notice(notice_id="commission:20000")
        unmatched = notice(
            notice_id="commission:19999",
            start="2026-07-03",
            end="2026-07-04",
        )
        payload = registry(matched, unmatched)

        reconcile_commission_notices(payload, [event("published")])

        for item in payload["notices"]:
            self.assertIn("coverage", item)
            validate_notice_coverage(item)

    def test_multiple_events_with_one_wave_use_deterministic_representative(self):
        first = event(
            "one-wave-a",
            commissioner="Client X",
            publication_date="2026-07-03",
        )
        second = event(
            "one-wave-b",
            commissioner="Client X",
            publication_date="2026-07-03",
        )
        expected_event_id = min(first["event_id"], second["event_id"])

        for published in ((first, second), (second, first)):
            with self.subTest(
                input_event_ids=[item["event_id"] for item in published]
            ):
                item = notice(
                    sample_size=1000,
                    commissioner="Client X",
                    publication_date="2026-07-03",
                )

                reconcile_commission_notices(registry(item), published)

                self.assertEqual(item["coverage"]["state"], "reconciled")
                self.assertEqual(
                    item["coverage"]["method"],
                    "exact_pollster_fieldwork_round",
                )
                self.assertEqual(
                    item["coverage"]["matched_event_ids"],
                    [expected_event_id],
                )

    def test_round_incompatibility_fails_closed(self):
        cases = (
            (
                notice(),
                event("second-round", round_name="second_round"),
                "no_exact_published_wave",
            ),
            (
                notice(confirmed_rounds=["second_round"]),
                event("first-round"),
                "no_compatible_published_round",
            ),
        )

        for item, published, expected_method in cases:
            with self.subTest(expected_method=expected_method):
                reconcile_commission_notices(registry(item), [published])

                self.assertEqual(item["coverage"]["state"], "unresolved")
                self.assertEqual(
                    item["coverage"]["method"],
                    expected_method,
                )

    def test_zero_match_optional_metadata_is_non_dispositive(self):
        item = notice(sample_size=999, commissioner="Client Y")
        expected = event(
            "wave-b",
            source="https://b.example/poll",
            sample_size=1200,
            commissioner="Client Y",
        )
        published = [
            event(
                "wave-a",
                source="https://a.example/poll",
                sample_size=1000,
                commissioner="Client X",
            ),
            expected,
        ]

        reconcile_commission_notices(registry(item), published)

        self.assertEqual(item["coverage"]["state"], "reconciled")
        self.assertEqual(
            item["coverage"]["matched_event_ids"],
            [expected["event_id"]],
        )

    def test_pollster_mismatch_does_not_reconcile(self):
        item = notice(pollster="Ifop")

        reconcile_commission_notices(
            registry(item),
            [event("wrong-pollster", pollster="Ipsos")],
        )

        self.assertEqual(item["coverage"]["state"], "unresolved")

    def test_date_incompatibility_does_not_reconcile(self):
        item = notice(start="2026-07-01", end="2026-07-03")

        reconcile_commission_notices(
            registry(item),
            [event("wrong-date", start="2026-07-01", end="2026-07-02")],
        )

        self.assertEqual(item["coverage"]["state"], "unresolved")

    def test_irrelevant_notice_has_no_state_and_no_warning(self):
        item = notice(classification="excluded_non_voting")
        payload = registry(item)

        reconcile_commission_notices(payload, [])

        self.assertNotIn("coverage", item)
        self.assertEqual(coverage_warnings(payload), [])
        self.assertEqual(
            coverage_summary(payload),
            {
                "relevant": 0,
                "parsed": 0,
                "reconciled": 0,
                "unresolved": 0,
                "unresolved_notice_ids": [],
            },
        )


class CurrentCommissionCoverageRegressionTests(unittest.TestCase):
    def test_tracked_registry_supports_legacy_and_reconciled_deployment_states(
        self,
    ):
        root = Path(__file__).resolve().parent
        payload = json.loads(
            (root / "commission_notice_registry.json").read_text(
                encoding="utf-8"
            )
        )
        events = json.loads(
            (root / "polls.json").read_text(encoding="utf-8")
        )
        stored = {
            item["notice_id"]: item.get("coverage")
            for item in payload["notices"]
        }

        relevant = [
            item
            for item in payload["notices"]
            if item["classification"] in {"eligible", "unsupported"}
        ]
        if any("coverage" not in item for item in relevant):
            self.assertEqual(
                coverage_summary(payload),
                {
                    "relevant": 15,
                    "parsed": 0,
                    "reconciled": 0,
                    "unresolved": 15,
                    "unresolved_notice_ids": [
                        item["notice_id"] for item in relevant
                    ],
                },
            )
            self.assertEqual(len(coverage_warnings(payload)), 15)
            self.assertEqual(
                {
                    item["notice_id"]: item.get("coverage")
                    for item in payload["notices"]
                },
                stored,
            )
            return

        summary = reconcile_commission_notices(payload, events)

        self.assertEqual(
            summary,
            {
                "relevant": 15,
                "parsed": 3,
                "reconciled": 12,
                "unresolved": 0,
                "unresolved_notice_ids": [],
            },
        )
        self.assertEqual(
            {
                item["notice_id"]: item.get("coverage")
                for item in payload["notices"]
            },
            stored,
        )


if __name__ == "__main__":
    unittest.main()
