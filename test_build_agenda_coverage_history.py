from __future__ import annotations

import copy
import io
import json
import subprocess
import unittest
import uuid
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import build_agenda_coverage_history as builder
from agenda_page_contract import (
    AGENDA_DEFINITIONS,
    AgendaPageContractError,
    validate_agenda_coverage_history,
)


ROOT = Path(__file__).resolve().parent


class MemoryJsonPath:
    def __init__(self, payload: dict):
        self.payload = payload

    def read_text(self, *, encoding: str) -> str:
        self.assert_utf8(encoding)
        return json.dumps(self.payload)

    @staticmethod
    def assert_utf8(encoding: str) -> None:
        if encoding != "utf-8":
            raise AssertionError("history builder must read JSON as UTF-8")


def snapshot(
    *,
    generated_at: str = "2026-01-31T12:00:00Z",
    omit: set[str] | None = None,
) -> dict:
    generated_day = date.fromisoformat(generated_at[:10])
    start = generated_day - timedelta(days=29)
    dates = [(start + timedelta(days=offset)).isoformat() for offset in range(30)]
    topics = []
    for topic_index, definition in enumerate(AGENDA_DEFINITIONS):
        if definition.topic_id in (omit or set()):
            continue
        points = []
        for day_index, day in enumerate(dates):
            value = 0
            if definition.topic_id == "selection_strategy" and day_index in (0, 1):
                # Deliberately retained classification without any headline input.
                value = 2 if day_index == 0 else 1
            if definition.topic_id == "polls_race" and day_index == 2:
                value = 1
            points.append(
                {"date": day, "item_count": value, "source_day_count": value}
            )
        topics.append(
            {
                "id": definition.topic_id,
                "label": definition.label_en,
                "item_count": sum(point["item_count"] for point in points),
                "source_day_count": sum(point["source_day_count"] for point in points),
                "daily_activity": points,
            }
        )
    supporting_topics = []
    for topic in topics:
        observed = [point for point in topic["daily_activity"] if point["item_count"]]
        supporting_topics.append({"id": topic["id"], "supporting_items": [
            {"id": topic["id"] + point["date"], "publisher": "Retained publisher",
             "headline": "Retained observation", "url": "https://example.org/" + topic["id"] + "/" + point["date"],
             "published_at": point["date"] + "T00:00:00Z"} for point in observed
        ]})
    return {
        "generated_at": generated_at,
        "campaign_agenda": {
            "topics": supporting_topics,
            "evolution": {
                "period_days": 30,
                "period_start": dates[0],
                "period_end": dates[-1],
                "period_end_partial": True,
                "topics": topics,
            }
        },
    }


class AgendaCoverageHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads(
            (ROOT / "agenda_coverage_history.json").read_text(encoding="utf-8")
        )

    def build_synthetic(self, current: dict | None = None) -> dict:
        current = current or snapshot()
        observation = {
            "commit": "a" * 40,
            "committed_at": datetime(2026, 1, 31, tzinfo=timezone.utc),
            "blob": "b" * 40,
        }
        with (
            patch.object(
                builder,
                "_first_inventory_timestamp",
                return_value=(
                    datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                    "inventory-commit",
                ),
            ),
            patch.object(
                builder,
                "_campaign_introduction_date",
                return_value=date(2026, 1, 1),
            ),
            patch.object(
                builder,
                "_history_observations",
                return_value=[observation],
            ),
            patch.object(
                builder,
                "_read_blobs",
                return_value=[(observation, current)],
            ),
        ):
            return builder.build_history_payload(
                root=ROOT, news_wire_path=MemoryJsonPath(current)
            )

    def test_materialized_evidence_has_retained_authority_and_exact_source_values(self):
        section = self.artifact["historical_evidence"]
        items = section["items"]
        self.assertEqual(len(items), 6)
        self.assertEqual({item["topic_id"] for item in items}, {topic["id"] for topic in self.artifact["topics"]})
        self.assertEqual(items, sorted(items, key=lambda item: (item["date"], item["published_at"], str(item["id"])), reverse=True))
        authority = {point["date"]: point["source_snapshot_at"] for point in self.artifact["daily"]}
        snapshots = {}
        for item in items:
            self.assertEqual(item["source_snapshot_at"], authority[item["date"]])
            commit = item["source_commit"]
            if commit not in snapshots:
                snapshots[commit] = json.loads(subprocess.check_output(["git", "show", f"{commit}:news_wire.json"], cwd=ROOT))
            payload = snapshots[commit]
            self.assertEqual(payload["generated_at"], item["source_snapshot_at"])
            topic = next(topic for topic in payload["campaign_agenda"]["topics"] if topic["id"] == item["topic_id"])
            original = next(row for row in topic["supporting_items"] if row["id"] == item["id"] and row["url"] == item["url"])
            for field in ("publisher", "published_at", "headline", "url"):
                self.assertEqual(item[field], original[field])

    def test_evidence_selection_retains_source_day_peak_tie_break_and_output_order(self):
        retained = snapshot()
        points = retained["campaign_agenda"]["evolution"]["topics"][1]["daily_activity"]
        topic_data = {"id": "selection_strategy", "active_days": 2, "daily": points}
        daily = [{"date": point["date"], "source_snapshot_at": retained["generated_at"]} for point in points[:-1]]
        observation = {"commit": "a" * 40}
        select = lambda: builder._historical_evidence([(observation, retained)], daily, [topic_data])["items"][0]
        row = select()
        self.assertEqual(row["topic_id"], "selection_strategy")
        self.assertEqual(row["date"], "2026-01-02")
        topic = retained["campaign_agenda"]["topics"][1]
        earlier = copy.deepcopy(topic["supporting_items"][0])
        earlier.update(id="a-earlier", published_at="2026-01-02T00:00:00Z", url="https://example.org/unchanged?x=1&y=2")
        topic["supporting_items"].append(earlier)
        selected = select()
        self.assertEqual(selected["id"], "a-earlier")
        self.assertEqual(selected["url"], earlier["url"])

    def test_evidence_has_no_current_only_fallback_or_unknown_topic(self):
        topic = {"id": "selection_strategy", "active_days": 1,
                 "daily": [{"date": "2026-01-02", "source_day_count": 2}]}
        daily = [{"date": "2026-01-02", "source_snapshot_at": "2026-01-31T12:00:00Z"}]
        with self.assertRaisesRegex(builder.AgendaCoverageHistoryError, "authoritative retained"):
            builder._historical_evidence([], daily, [topic])
        wrong = snapshot(generated_at="2026-01-30T12:00:00Z")
        with self.assertRaisesRegex(builder.AgendaCoverageHistoryError, "authoritative retained"):
            builder._historical_evidence([({"commit": "a" * 40}, wrong)], daily, [topic])

    def test_published_artifact_is_valid_contiguous_and_excludes_partial_day(self):
        index = validate_agenda_coverage_history(self.artifact)
        period = self.artifact["period"]
        start = date.fromisoformat(period["start_date"])
        end = date.fromisoformat(period["end_date"])
        self.assertEqual(period["days"], (end - start).days + 1)
        self.assertEqual(
            end,
            date.fromisoformat(self.artifact["data_as_of"][:10])
            - timedelta(days=1),
        )
        self.assertTrue(period["current_utc_day_excluded"])
        self.assertEqual(tuple(index), tuple(item.topic_id for item in AGENDA_DEFINITIONS))

    def test_absent_historical_canonical_topic_is_zero_filled(self):
        retained = snapshot(omit={"positioning_integrity"})
        days = builder._snapshot_days(
            retained,
            start=date(2026, 1, 2),
            end=date(2026, 1, 30),
        )
        self.assertEqual(len(days), 29)
        self.assertTrue(
            all(
                point["topics"]["positioning_integrity"]
                == {"item_count": 0, "source_day_count": 0}
                for point in days.values()
            )
        )

    def test_unknown_and_duplicate_historical_topics_fail_closed(self):
        unknown = snapshot()
        unknown["campaign_agenda"]["evolution"]["topics"][0]["id"] = (
            "economy_public_finances"
        )
        with self.assertRaisesRegex(builder.AgendaCoverageHistoryError, "unknown taxonomy"):
            builder._snapshot_days(
                unknown, start=date(2026, 1, 2), end=date(2026, 1, 30)
            )

        duplicate = snapshot()
        duplicate["campaign_agenda"]["evolution"]["topics"].append(
            copy.deepcopy(duplicate["campaign_agenda"]["evolution"]["topics"][0])
        )
        with self.assertRaisesRegex(builder.AgendaCoverageHistoryError, "duplicate topic"):
            builder._snapshot_days(
                duplicate, start=date(2026, 1, 2), end=date(2026, 1, 30)
            )

    def test_single_label_item_and_source_day_denominators_reconcile(self):
        for index, day in enumerate(self.artifact["daily"]):
            topic_points = [topic["daily"][index] for topic in self.artifact["topics"]]
            self.assertEqual(
                sum(point["item_count"] for point in topic_points),
                day["total_classified_agenda_items"],
            )
            self.assertEqual(
                sum(point["source_day_count"] for point in topic_points),
                day["total_agenda_topic_source_days"],
            )
            self.assertAlmostEqual(
                sum(point["topic_item_share"] for point in topic_points),
                1.0 if day["total_classified_agenda_items"] else 0.0,
            )
            self.assertAlmostEqual(
                sum(point["topic_source_day_share"] for point in topic_points),
                1.0 if day["total_agenda_topic_source_days"] else 0.0,
            )

    def test_reconstruction_retains_published_classifications_without_headlines(self):
        payload = self.build_synthetic()
        selection = next(
            topic for topic in payload["topics"] if topic["id"] == "selection_strategy"
        )
        self.assertEqual(selection["total_items"], 3)
        self.assertEqual(selection["total_source_days"], 3)
        self.assertNotIn("relevant_news", snapshot())
        self.assertIn(
            "never reclassify old headlines",
            payload["reconstruction"]["historical_classifier_policy"],
        )

    def test_repeated_generation_is_byte_identical(self):
        first = builder.serialize_history(self.build_synthetic())
        second = builder.serialize_history(self.build_synthetic())
        self.assertEqual(first, second)

    def test_check_mode_detects_stale_artifact(self):
        payload = self.build_synthetic()
        output = ROOT / f".agenda-history-check-{uuid.uuid4().hex}.json"
        self.addCleanup(output.unlink, missing_ok=True)
        output.write_bytes(b"stale\n")
        with patch.object(builder, "build_history_payload", return_value=payload):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    builder.main(["--output", str(output), "--check"]),
                    1,
                )
                output.write_bytes(builder.serialize_history(payload))
                self.assertEqual(
                    builder.main(["--output", str(output), "--check"]),
                    0,
                )

    def test_candidate_history_is_rejected_as_media_volume_history(self):
        candidate_history = json.loads(
            (ROOT / "candidate_agenda_history.json").read_text(encoding="utf-8")
        )
        with self.assertRaises(AgendaPageContractError):
            validate_agenda_coverage_history(candidate_history)

    def test_missing_required_complete_day_fails_closed(self):
        current = snapshot(generated_at="2026-02-01T12:00:00Z")
        observation = {
            "commit": "a" * 40,
            "committed_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
            "blob": "b" * 40,
        }
        with (
            patch.object(
                builder,
                "_first_inventory_timestamp",
                return_value=(
                    datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                    "inventory-commit",
                ),
            ),
            patch.object(
                builder,
                "_campaign_introduction_date",
                return_value=date(2026, 1, 1),
            ),
            patch.object(
                builder, "_history_observations", return_value=[observation]
            ),
            patch.object(
                builder,
                "_read_blobs",
                return_value=[(observation, current)],
            ),
        ):
            with self.assertRaisesRegex(
                builder.AgendaCoverageHistoryError,
                "do not cover complete days: 2026-01-02",
            ):
                builder.build_history_payload(
                    root=ROOT, news_wire_path=MemoryJsonPath(current)
                )


if __name__ == "__main__":
    unittest.main()
