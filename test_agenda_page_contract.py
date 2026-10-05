from __future__ import annotations

import copy
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from agenda_page_contract import (
    AGENDA_DEFINITIONS,
    CANONICAL_AGENDA_IDS,
    CURRENT_SOURCE_DAY_MIN,
    HISTORICAL_EVIDENCE_SELECTION_RULE,
    HISTORICAL_EVIDENCE_SOURCE,
    validate_agenda_coverage_history,
    POLICY_AGENDA_IDS,
    AgendaPageContractError,
    agenda_manifest_payload,
    project_agenda_pages,
    validate_agenda_manifest,
    validate_candidate_history_compatibility,
)
from fetch_news_wire import (
    CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS,
    CAMPAIGN_AGENDA_TOPICS,
)


ROOT = Path(__file__).resolve().parent


def synthetic_history(
    topic_id: str,
    source_day_counts: list[int],
) -> dict:
    start = date(2026, 1, 1)
    day_count = 30
    dates = [(start + timedelta(days=offset)).isoformat() for offset in range(day_count)]
    counts = {
        definition.topic_id: [0] * day_count for definition in AGENDA_DEFINITIONS
    }
    counts[topic_id][: len(source_day_counts)] = source_day_counts
    daily = []
    for index, day in enumerate(dates):
        total = sum(values[index] for values in counts.values())
        daily.append(
            {
                "date": day,
                "total_classified_agenda_items": total,
                "total_agenda_topic_source_days": total,
                "source_snapshot_at": "2026-01-31T12:00:00Z",
            }
        )
    topics = []
    for definition in AGENDA_DEFINITIONS:
        points = []
        for index, day in enumerate(dates):
            value = counts[definition.topic_id][index]
            denominator = daily[index]["total_classified_agenda_items"]
            points.append(
                {
                    "date": day,
                    "item_count": value,
                    "source_day_count": value,
                    "total_classified_agenda_items": denominator,
                    "total_agenda_topic_source_days": denominator,
                    "topic_item_share": value / denominator if denominator else 0.0,
                    "topic_source_day_share": value / denominator if denominator else 0.0,
                }
            )
        observed = [point for point in points if point["item_count"]]
        peak = min(
            points,
            key=lambda point: (
                -point["source_day_count"],
                -point["item_count"],
                point["date"],
            ),
        )
        maximum = sum(point["source_day_count"] for point in points)
        topics.append(
            {
                "id": definition.topic_id,
                "labels": {"fr": definition.label_fr, "en": definition.label_en},
                "total_items": sum(point["item_count"] for point in points),
                "total_source_days": maximum,
                "active_days": len(observed),
                "first_observation": observed[0]["date"] if observed else None,
                "last_observation": observed[-1]["date"] if observed else None,
                "peak_day": {
                    "date": peak["date"],
                    "item_count": peak["item_count"],
                    "source_day_count": peak["source_day_count"],
                },
                "maximum_rolling_30d_source_days": maximum,
                "historical_qualified": maximum >= CURRENT_SOURCE_DAY_MIN,
                "daily": points,
            }
        )
    return {
        "schema_version": "1.0",
        "data_as_of": "2026-01-31T12:00:00Z",
        "period": {
            "start_date": dates[0],
            "end_date": dates[-1],
            "days": day_count,
            "day_boundary": "UTC",
            "current_utc_day_excluded": True,
        },
        "reconstruction": {
            "classification_source": (
                "retained news_wire.json campaign_agenda.evolution snapshots"
            ),
            "prohibited_proxy": (
                "candidate_agenda_history.json is not used as media-volume history"
            ),
        },
        "denominator": {"single_label": True},
        "daily": daily,
        "topics": topics,
        "historical_evidence": {
            "source": HISTORICAL_EVIDENCE_SOURCE,
            "selection_rule": HISTORICAL_EVIDENCE_SELECTION_RULE,
            "items": [
                {"id": topic["id"], "topic_id": topic["id"], "publisher": "Retained publisher",
                 "headline": "Retained classified observation", "url": "https://example.org/" + topic["id"],
                 "date": topic["peak_day"]["date"], "published_at": topic["peak_day"]["date"] + "T00:00:00Z",
                 "source_snapshot_at": "2026-01-31T12:00:00Z", "source_commit": "a" * 40}
                for topic in topics if topic["active_days"] > 0
            ],
        },
    }


class AgendaPageContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.news = json.loads((ROOT / "news_wire.json").read_text(encoding="utf-8"))
        cls.history = json.loads(
            (ROOT / "agenda_coverage_history.json").read_text(encoding="utf-8")
        )
        cls.candidate_history = json.loads(
            (ROOT / "candidate_agenda_history.json").read_text(encoding="utf-8")
        )

    @staticmethod
    def weaken_current(news: dict, topic_id: str) -> None:
        topic = next(
            topic for topic in news["campaign_agenda"]["topics"] if topic["id"] == topic_id
        )
        topic["item_count"] = 0
        topic["publisher_count"] = 0
        topic["source_day_count"] = 0
        topic["display_eligible"] = False

    def test_locked_taxonomy_is_exactly_six_ids_in_source_order(self):
        source = tuple(topic["id"] for topic in CAMPAIGN_AGENDA_TOPICS)
        self.assertEqual(len(CANONICAL_AGENDA_IDS), 6)
        self.assertEqual(CANONICAL_AGENDA_IDS, source)

    def test_english_labels_match_source_and_french_labels_match_locale(self):
        source = {topic["id"]: topic["label"] for topic in CAMPAIGN_AGENDA_TOPICS}
        locale = (ROOT / "locales" / "fr.js").read_text(encoding="utf-8")
        for definition in AGENDA_DEFINITIONS:
            self.assertEqual(definition.label_en, source[definition.topic_id])
            self.assertIn(
                f'"agenda_topic.{definition.topic_id}": "{definition.label_fr}"',
                locale,
            )

    def test_historical_evidence_schema_and_invalid_values_fail_closed(self):
        artifact = json.loads((ROOT / "agenda_coverage_history.json").read_text(encoding="utf-8"))
        validate_agenda_coverage_history(artifact)
        mutations = {
            "topic_id": "unknown_topic", "url": "", "publisher": " ", "headline": "",
            "date": "2026-02-30", "published_at": "invalid", "source_snapshot_at": "1900-01-01T00:00:00Z",
            "source_commit": "invalid", "id": "",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                malformed = copy.deepcopy(artifact)
                malformed["historical_evidence"]["items"][0][field] = value
                with self.assertRaises(AgendaPageContractError):
                    validate_agenda_coverage_history(malformed)
        for url in ("file:///example", "https://", "javascript:alert(1)", "https://example.org/bad url"):
            malformed = copy.deepcopy(artifact)
            malformed["historical_evidence"]["items"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(AgendaPageContractError):
                validate_agenda_coverage_history(malformed)

    def test_historical_evidence_census_order_and_authority_fail_closed(self):
        artifact = json.loads((ROOT / "agenda_coverage_history.json").read_text(encoding="utf-8"))
        for case in ("missing_section", "missing_item", "duplicate_topic", "reverse_order", "wrong_authority", "wrong_rule", "wrong_date"):
            malformed = copy.deepcopy(artifact)
            section = malformed["historical_evidence"]
            if case == "missing_section": del malformed["historical_evidence"]
            elif case == "missing_item": section["items"].pop()
            elif case == "duplicate_topic": section["items"].append(copy.deepcopy(section["items"][0]))
            elif case == "reverse_order": section["items"].reverse()
            elif case == "wrong_authority": section["source"] = "candidate associations"
            elif case == "wrong_rule": section["selection_rule"] = "current-only evidence"
            elif case == "wrong_date": section["items"][0]["date"] = "1900-01-01"
            with self.subTest(case=case), self.assertRaises(AgendaPageContractError):
                validate_agenda_coverage_history(malformed)

    def test_historical_evidence_allows_preceding_snapshot_but_rejects_later_snapshot(self):
        artifact = synthetic_history(
            "selection_strategy",
            [1, 1],
        )

        item = artifact["historical_evidence"]["items"][0]
        day = item["date"]

        daily = next(
            row
            for row in artifact["daily"]
            if row["date"] == day
        )

        daily["source_snapshot_at"] = (
            "2026-01-30T12:00:00Z"
        )
        item["source_snapshot_at"] = (
            "2026-01-30T11:00:00Z"
        )

        validate_agenda_coverage_history(artifact)

        malformed = copy.deepcopy(artifact)
        malformed["historical_evidence"]["items"][0][
            "source_snapshot_at"
        ] = "2026-01-30T13:00:00Z"

        with self.assertRaisesRegex(
            AgendaPageContractError,
            "exceeds retained history authority",
        ):
            validate_agenda_coverage_history(malformed)

    def test_bilingual_slugs_are_unique(self):
        self.assertEqual(
            len({definition.slug_fr for definition in AGENDA_DEFINITIONS}), 6
        )
        self.assertEqual(
            len({definition.slug_en for definition in AGENDA_DEFINITIONS}), 6
        )

    def test_unknown_and_duplicate_current_topics_fail_closed(self):
        unknown = copy.deepcopy(self.news)
        row = copy.deepcopy(unknown["campaign_agenda"]["topics"][0])
        row["id"] = "economy_public_finances"
        unknown["campaign_agenda"]["topics"].append(row)
        with self.assertRaisesRegex(AgendaPageContractError, "unknown taxonomy"):
            project_agenda_pages(unknown, self.history)

        duplicate = copy.deepcopy(self.news)
        duplicate["campaign_agenda"]["topics"].append(
            copy.deepcopy(duplicate["campaign_agenda"]["topics"][0])
        )
        with self.assertRaisesRegex(AgendaPageContractError, "duplicate topic"):
            project_agenda_pages(duplicate, self.history)

    def test_missing_current_canonical_topic_is_zero_not_taxonomy_removal(self):
        topic_id = CANONICAL_AGENDA_IDS[0]
        news = copy.deepcopy(self.news)
        news["campaign_agenda"]["topics"] = [
            topic for topic in news["campaign_agenda"]["topics"] if topic["id"] != topic_id
        ]
        news["campaign_agenda"]["evolution"]["topics"] = [
            topic
            for topic in news["campaign_agenda"]["evolution"]["topics"]
            if topic["id"] != topic_id
        ]
        projection = project_agenda_pages(news, self.history)
        topic = next(row for row in projection["topics"] if row["topic_id"] == topic_id)
        self.assertFalse(topic["qualification"]["current"])
        self.assertIsNone(topic["current_base_projection"])
        self.assertIsNone(topic["current_evolution_projection"])
        self.assertEqual(topic["lifecycle"], "historical")

    def test_current_qualification_is_exact_existing_two_source_day_rule(self):
        self.assertEqual(CURRENT_SOURCE_DAY_MIN, 2)
        self.assertEqual(
            CURRENT_SOURCE_DAY_MIN, CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
        )
        topic_id = CANONICAL_AGENDA_IDS[0]
        news = copy.deepcopy(self.news)
        topic = next(
            row for row in news["campaign_agenda"]["topics"] if row["id"] == topic_id
        )
        topic["item_count"] = 100
        topic["publisher_count"] = 100
        topic["source_day_count"] = 1
        topic["display_eligible"] = False
        projected = project_agenda_pages(news, self.history)
        row = next(item for item in projected["topics"] if item["topic_id"] == topic_id)
        self.assertFalse(row["qualification"]["current"])

        topic["item_count"] = 2
        topic["publisher_count"] = 0
        topic["source_day_count"] = 2
        topic["display_eligible"] = True
        projected = project_agenda_pages(news, self.history)
        row = next(item for item in projected["topics"] if item["topic_id"] == topic_id)
        self.assertTrue(row["qualification"]["current"])

    def test_historical_qualification_uses_same_rolling_source_day_rule(self):
        topic_id = CANONICAL_AGENDA_IDS[0]
        news = copy.deepcopy(self.news)
        self.weaken_current(news, topic_id)
        weak = synthetic_history(topic_id, [1])
        projected = project_agenda_pages(news, weak)
        row = next(item for item in projected["topics"] if item["topic_id"] == topic_id)
        self.assertFalse(row["qualification"]["historical"])
        self.assertEqual(row["lifecycle"], "unpublished")

        qualified = synthetic_history(topic_id, [1, 1])
        projected = project_agenda_pages(news, qualified)
        row = next(item for item in projected["topics"] if item["topic_id"] == topic_id)
        self.assertTrue(row["qualification"]["historical"])
        self.assertEqual(row["lifecycle"], "historical")

    def test_previously_public_weak_topic_becomes_dormant(self):
        topic_id = CANONICAL_AGENDA_IDS[0]
        news = copy.deepcopy(self.news)
        self.weaken_current(news, topic_id)
        previous = {"pages": [{"topic_id": topic_id}]}
        projected = project_agenda_pages(
            news,
            synthetic_history(topic_id, [1]),
            previous_manifest=previous,
        )
        row = next(item for item in projected["topics"] if item["topic_id"] == topic_id)
        self.assertTrue(row["public"])
        self.assertEqual(row["lifecycle"], "dormant")

    def test_policy_agenda_ids_are_never_exposed(self):
        self.assertTrue(POLICY_AGENDA_IDS)
        self.assertFalse(set(CANONICAL_AGENDA_IDS) & POLICY_AGENDA_IDS)
        projection = project_agenda_pages(self.news, self.history)
        self.assertFalse(
            {topic["topic_id"] for topic in projection["topics"]} & POLICY_AGENDA_IDS
        )

    def test_candidate_history_is_compatible_but_remains_a_separate_source(self):
        validate_candidate_history_compatibility(self.candidate_history)
        projection = project_agenda_pages(
            self.news,
            self.history,
            candidate_history=self.candidate_history,
        )
        self.assertEqual(
            projection["source"]["candidate_associations"],
            "candidate_agenda_history.json",
        )
        self.assertNotEqual(
            projection["source"]["history"],
            projection["source"]["candidate_associations"],
        )

    def test_manifest_projection_has_locked_lifecycle_and_routes(self):
        projection = project_agenda_pages(self.news, self.history)
        manifest = agenda_manifest_payload(projection)
        validate_agenda_manifest(manifest)
        self.assertEqual(manifest["public_topic_count"], 6)
        self.assertEqual(manifest["page_count"], 28)
        self.assertEqual(manifest["hubs"]["fr"], "/agenda/")
        self.assertEqual(manifest["history_hubs"]["en"], "/en/agenda/history/")

    def test_unknown_previously_public_topic_fails_closed(self):
        with self.assertRaisesRegex(AgendaPageContractError, "unknown taxonomy"):
            project_agenda_pages(
                self.news,
                self.history,
                previous_manifest={"pages": [{"topic_id": "not_canonical"}]},
            )


if __name__ == "__main__":
    unittest.main()
