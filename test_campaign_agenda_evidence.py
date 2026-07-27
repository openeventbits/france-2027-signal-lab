import copy
import unittest
from datetime import datetime, timedelta, timezone

from fetch_news_wire import (
    CAMPAIGN_AGENDA_SUPPORT_LIMIT,
    build_campaign_agenda,
    validate_campaign_agenda_topic,
)


class CampaignAgendaEvidenceTests(unittest.TestCase):
    @staticmethod
    def item(index, published_at, publisher):
        return {
            "id": f"item-{index:02d}",
            "publisher": publisher,
            "published_at": published_at,
            "headline": (
                "Présidentielle 2027 : "
                f"annonce de candidature {index:02d}"
            ),
            "url": (
                f"https://example.test/topic/{index:02d}"
            ),
            "candidates": ["Gabriel Attal"],
            "development_category": (
                "candidacies_endorsements"
            ),
            "development_label": (
                "Candidacies and endorsements"
            ),
            "matched_terms": ["candidature"],
        }

    def build_items(self):
        anchor = datetime(
            2026,
            7,
            26,
            20,
            tzinfo=timezone.utc,
        )

        items = [
            self.item(
                index,
                (
                    anchor - timedelta(hours=index)
                ).isoformat().replace("+00:00", "Z"),
                (
                    "Le Monde"
                    if index % 2 == 0
                    else "Le Figaro"
                ),
            )
            for index in range(25)
        ]

        return items[::2] + items[1::2]

    def test_exports_twenty_items_and_reports_omissions(self):
        agenda = build_campaign_agenda(
            self.build_items(),
            window_days=30,
        )
        topic = agenda["topics"][0]

        self.assertEqual(
            CAMPAIGN_AGENDA_SUPPORT_LIMIT,
            20,
        )
        self.assertEqual(topic["item_count"], 25)
        self.assertEqual(
            topic["supporting_item_count"],
            20,
        )
        self.assertEqual(topic["omitted_item_count"], 5)
        self.assertEqual(
            len(topic["supporting_items"]),
            20,
        )
        self.assertEqual(
            [
                item["id"]
                for item in topic["supporting_items"]
            ],
            [
                f"item-{index:02d}"
                for index in range(20)
            ],
        )

        seen = set()
        validate_campaign_agenda_topic(
            topic,
            seen,
        )
        self.assertEqual(
            seen,
            {"candidacies_endorsements"},
        )

    def test_smaller_topics_export_all_evidence(self):
        agenda = build_campaign_agenda(
            self.build_items()[:7],
            window_days=30,
        )
        topic = agenda["topics"][0]

        self.assertEqual(topic["item_count"], 7)
        self.assertEqual(
            topic["supporting_item_count"],
            7,
        )
        self.assertEqual(
            topic["omitted_item_count"],
            0,
        )

    def test_equal_timestamps_use_stable_tie_breakers(self):
        published_at = "2026-07-26T12:00:00Z"
        items = [
            self.item(2, published_at, "Le Monde"),
            self.item(1, published_at, "Franceinfo"),
            self.item(0, published_at, "Le Figaro"),
        ]

        topic = build_campaign_agenda(
            items,
            window_days=30,
        )["topics"][0]

        self.assertEqual(
            [
                item["publisher"]
                for item in topic["supporting_items"]
            ],
            [
                "Franceinfo",
                "Le Figaro",
                "Le Monde",
            ],
        )

    def test_validator_rejects_contract_corruption(self):
        topic = build_campaign_agenda(
            self.build_items(),
            window_days=30,
        )["topics"][0]

        mutations = {
            "support count": lambda value: value.update(
                supporting_item_count=19
            ),
            "omitted count": lambda value: value.update(
                omitted_item_count=4
            ),
            "ordering": lambda value: value.update(
                supporting_items=list(
                    reversed(
                        value["supporting_items"]
                    )
                )
            ),
            "duplicate evidence": lambda value: value[
                "supporting_items"
            ].__setitem__(
                1,
                copy.deepcopy(
                    value["supporting_items"][0]
                ),
            ),
        }

        for label, mutate in mutations.items():
            with self.subTest(label=label):
                invalid = copy.deepcopy(topic)
                mutate(invalid)

                with self.assertRaises(RuntimeError):
                    validate_campaign_agenda_topic(
                        invalid,
                        set(),
                    )


if __name__ == "__main__":
    unittest.main()
