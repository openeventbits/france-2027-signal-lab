from __future__ import annotations

import copy
import json
import subprocess
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

from build_candidate_attention import (
    WikimediaFetchError,
    WikimediaPageviewsNotFoundError,
    build_candidate_attention_payload,
    build_fetch_plan,
    collect_wikimedia_observations,
    run_build,
    serialize_semantic_payload,
)
from candidate_attention_contract import (
    CandidateAttentionContractError,
    validate_candidate_attention,
)


ROOT = Path(__file__).resolve().parent
DATA_AS_OF = date(2026, 8, 6)
SOURCE_URL = (
    "https://fr.wikipedia.org/w/index.php?"
    "title=%C3%89lection+pr%C3%A9sidentielle+fran%C3%A7aise+de+2027"
    "&oldid=238417295"
)


def article(index: int) -> dict[str, object]:
    return {
        "page_id": 100000 + index,
        "title": f"Candidate {index:03d}",
        "url": f"https://fr.wikipedia.org/wiki/Candidate_{index:03d}",
    }


def candidate(
    index: int,
    *,
    tier: str = "main",
    presence: str = "present",
    has_article: bool = True,
) -> dict[str, object]:
    status_by_tier = {
        "main": "declared",
        "secondary": "active_potential",
        "hidden": "ruled_out",
    }
    return {
        "candidate_id": f"candidate-{index:03d}",
        "candidate_name": f"Candidate {index:03d}",
        "status": status_by_tier[tier],
        "display_tier": tier,
        "upstream_presence": presence,
        "wikipedia_article": article(index) if has_article else None,
        "previous_names": [],
        "status_as_of": "2026-08-06",
        "source_date": "2026-08-06",
        "source_url": SOURCE_URL,
        "source_title": "Élection présidentielle française de 2027",
        "source_publisher": "French Wikipedia",
        "status_note": "Listed in the accepted upstream revision.",
    }


def registry(rows: list[dict[str, object]]) -> dict[str, object]:
    ordered = sorted(
        rows,
        key=lambda row: (
            str(row["candidate_name"]).casefold(),
            row["candidate_id"],
        ),
    )
    return {
        "schema_version": "2.0",
        "status_as_of": "2026-08-06",
        "source": {
            "publisher": "French Wikipedia",
            "page_title": "Élection présidentielle française de 2027",
            "page_url": (
                "https://fr.wikipedia.org/wiki/"
                "%C3%89lection_pr%C3%A9sidentielle_fran%C3%A7aise_de_2027"
            ),
            "revision_id": 238417295,
            "revision_timestamp": "2026-08-06T20:48:08Z",
            "revision_url": SOURCE_URL,
        },
        "candidates": ordered,
    }


def series(value: int = 100) -> list[dict[str, object]]:
    start = DATA_AS_OF - timedelta(days=89)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "views": value + index,
        }
        for index in range(90)
    ]


def observations_for(
    candidacy: dict[str, object],
) -> dict[str, list[dict[str, object]]]:
    return {
        item["candidate_id"]: series(index * 10)
        for index, item in enumerate(
            build_fetch_plan(candidacy_payload=candidacy),
            start=1,
        )
        if item["wikipedia_article"] is not None
    }


def build_payload(
    candidacy: dict[str, object],
) -> dict[str, object]:
    return build_candidate_attention_payload(
        candidacy_payload=candidacy,
        registry_payload=None,
        observations_by_candidate=observations_for(candidacy),
        generated_at="2026-08-07T05:00:00Z",
        data_as_of=DATA_AS_OF.isoformat(),
    )


def pageview_payload(value: int = 100) -> dict[str, object]:
    return {
        "items": [
            {
                "timestamp": day["date"].replace("-", "") + "00",
                "views": value + index,
            }
            for index, day in enumerate(series(0))
        ]
    }


class CandidateAttentionDynamicUniverseTests(unittest.TestCase):
    def test_shared_active_projection_and_registry_order(self):
        rows = [
            candidate(1, tier="main"),
            candidate(2, tier="secondary"),
            candidate(3, tier="hidden"),
            candidate(4, tier="secondary", presence="temporarily_missing"),
            candidate(5, tier="main"),
        ]
        candidacy = registry(rows)

        with patch(
            "build_candidate_attention.active_candidate_records",
            wraps=__import__(
                "candidate_candidacy_status"
            ).active_candidate_records,
        ) as active_helper:
            plan = build_fetch_plan(candidacy_payload=candidacy)

        active_helper.assert_called_once_with(candidacy)
        self.assertEqual(
            [item["candidate_id"] for item in plan],
            ["candidate-001", "candidate-002", "candidate-005"],
        )

    def test_dynamic_counts_below_and_above_twenty(self):
        for count in (3, 21):
            with self.subTest(count=count):
                candidacy = registry(
                    [
                        candidate(
                            index,
                            tier="main" if index % 2 else "secondary",
                        )
                        for index in range(1, count + 1)
                    ]
                )
                payload = build_payload(candidacy)
                self.assertEqual(
                    payload["candidate_universe"]["count"],
                    count,
                )
                self.assertEqual(len(payload["candidates"]), count)

    def test_lifecycle_transitions_preserve_identity(self):
        base = candidate(1, tier="main")
        scenarios = (
            ("main", "present", True),
            ("secondary", "present", True),
            ("hidden", "present", False),
            ("secondary", "temporarily_missing", False),
            ("secondary", "present", True),
        )
        for tier, presence, expected_active in scenarios:
            row = copy.deepcopy(base)
            row["display_tier"] = tier
            row["status"] = {
                "main": "declared",
                "secondary": "active_potential",
                "hidden": "ruled_out",
            }[tier]
            row["upstream_presence"] = presence
            plan = build_fetch_plan(candidacy_payload=registry([row]))
            self.assertEqual(bool(plan), expected_active)
            if plan:
                self.assertEqual(plan[0]["candidate_id"], base["candidate_id"])


class CandidateAttentionV2EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.candidacy = registry(
            [
                candidate(1, tier="main"),
                candidate(2, tier="secondary"),
                candidate(3, tier="main", has_article=False),
                candidate(4, tier="hidden"),
                candidate(
                    5,
                    tier="secondary",
                    presence="temporarily_missing",
                ),
            ]
        )

    def test_registry_article_drives_fetch_and_null_article_skips_request(self):
        urls = []

        def fetcher(url):
            urls.append(url)
            return pageview_payload()

        result = collect_wikimedia_observations(
            candidacy_payload=self.candidacy,
            registry_payload=None,
            data_as_of=DATA_AS_OF,
            fetcher=fetcher,
            delay_seconds=0,
            sleeper=lambda _: None,
        )

        self.assertEqual(
            list(result),
            ["candidate-001", "candidate-002"],
        )
        self.assertEqual(len(urls), 2)
        self.assertIn("Candidate_001", unquote(urls[0]))
        self.assertIn("Candidate_002", unquote(urls[1]))
        self.assertNotIn("Candidate_003", " ".join(map(unquote, urls)))

    def test_v2_build_has_observed_and_explicit_unavailable_records(self):
        payload = build_payload(self.candidacy)
        validate_candidate_attention(
            payload,
            expected_candidates=[
                row
                for row in self.candidacy["candidates"]
                if row["candidate_id"] in {
                    "candidate-001",
                    "candidate-002",
                    "candidate-003",
                }
            ],
        )

        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(
            payload["candidate_universe"],
            {
                "source": "candidate_candidacy_status.json",
                "status_as_of": "2026-08-06",
                "rule": "active_monitoring_field",
                "count": 3,
                "article_eligible_count": 2,
                "unavailable_no_personal_article_count": 1,
            },
        )
        observed = payload["candidates"][0]
        self.assertEqual(observed["evidence_state"], "observed")
        self.assertEqual(observed["wikipedia_article"], article(1))
        self.assertEqual(len(observed["daily_series"]), 90)

        unavailable = payload["candidates"][2]
        self.assertEqual(
            unavailable["evidence_state"],
            "unavailable_no_personal_article",
        )
        self.assertIsNone(unavailable["wikipedia_article"])
        self.assertEqual(unavailable["daily_series"], [])
        for field, value in unavailable.items():
            if field in {
                "candidate_id",
                "candidate_name",
                "evidence_state",
                "wikipedia_article",
                "daily_series",
            }:
                continue
            self.assertIsNone(value, field)

        self.assertEqual(
            payload["validation"]["observed_candidate_count"],
            2,
        )
        self.assertEqual(
            payload["validation"]["unavailable_candidate_count"],
            1,
        )

    def test_v2_run_does_not_load_missing_legacy_mapping(self):
        observations = observations_for(self.candidacy)
        with (
            patch(
                "build_candidate_attention.load_candidate_candidacy_status",
                return_value=self.candidacy,
            ),
            patch(
                "build_candidate_attention._load_json_object",
                side_effect=AssertionError("legacy mapping was accessed"),
            ),
            patch(
                "build_candidate_attention.collect_wikimedia_observations",
                return_value=observations,
            ),
            patch("build_candidate_attention.atomic_write_bytes"),
        ):
            payload = run_build(
                candidacy_path="registry-v2.json",
                registry_path="missing-legacy-map.json",
                output_path="unused.json",
                data_as_of=DATA_AS_OF.isoformat(),
                generated_at="2026-08-07T05:00:00Z",
                delay_seconds=0,
            )
        self.assertEqual(payload["candidate_universe"]["count"], 3)

    def test_transient_or_404_failure_is_not_converted_to_unavailable(self):
        one = registry([candidate(1)])

        def fetcher(_url):
            raise WikimediaFetchError(
                "http_4xx",
                "HTTP 404",
                status=404,
                attempts=1,
            )

        with self.assertRaises(WikimediaPageviewsNotFoundError):
            collect_wikimedia_observations(
                candidacy_payload=one,
                registry_payload=None,
                data_as_of=DATA_AS_OF,
                fetcher=fetcher,
                delay_seconds=0,
                sleeper=lambda _: None,
            )

    def test_candidate_gaining_article_moves_to_observed(self):
        without = registry([candidate(1, has_article=False)])
        unavailable = build_payload(without)

        with_article = registry([candidate(1, has_article=True)])
        observed = build_payload(with_article)

        self.assertEqual(
            unavailable["candidates"][0]["candidate_id"],
            observed["candidates"][0]["candidate_id"],
        )
        self.assertEqual(
            unavailable["candidates"][0]["evidence_state"],
            "unavailable_no_personal_article",
        )
        self.assertEqual(
            observed["candidates"][0]["evidence_state"],
            "observed",
        )
        self.assertNotEqual(
            serialize_semantic_payload(unavailable),
            serialize_semantic_payload(observed),
        )


class CandidateAttentionV2ContractTests(unittest.TestCase):
    def setUp(self):
        self.candidacy = registry(
            [candidate(1), candidate(2, has_article=False)]
        )
        self.payload = build_payload(self.candidacy)

    def assert_invalid(self, mutate):
        changed = copy.deepcopy(self.payload)
        mutate(changed)
        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(changed)

    def test_observed_series_and_arithmetic_remain_strict(self):
        cases = (
            lambda value: value["candidates"][0]["daily_series"].pop(),
            lambda value: value["candidates"][0]["daily_series"].__setitem__(
                1,
                copy.deepcopy(value["candidates"][0]["daily_series"][0]),
            ),
            lambda value: value["candidates"][0]["daily_series"][0].__setitem__(
                "views",
                -1,
            ),
            lambda value: value["candidates"][0].__setitem__(
                "latest_7_views",
                value["candidates"][0]["latest_7_views"] + 1,
            ),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_unavailable_contract_rejects_fabricated_zero(self):
        self.assert_invalid(
            lambda value: value["candidates"][1].__setitem__(
                "latest_7_views",
                0,
            )
        )
        self.assert_invalid(
            lambda value: value["candidates"][1].__setitem__(
                "daily_series",
                [{"date": "2026-08-06", "views": 0}],
            )
        )

    def test_registry_article_identity_mismatch_rejects(self):
        changed = copy.deepcopy(self.payload)
        changed["candidates"][0]["wikipedia_article"]["page_id"] += 1
        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(
                changed,
                expected_candidates=self.candidacy["candidates"],
            )

    def test_semantic_no_churn_and_material_changes(self):
        timestamp_only = copy.deepcopy(self.payload)
        timestamp_only["generated_at"] = "2026-08-07T06:00:00Z"
        self.assertEqual(
            serialize_semantic_payload(self.payload),
            serialize_semantic_payload(timestamp_only),
        )

        mutations = (
            lambda value: value["candidates"][0]["daily_series"][-1].__setitem__(
                "views",
                value["candidates"][0]["daily_series"][-1]["views"] + 1,
            ),
            lambda value: value["candidates"][0]["wikipedia_article"].__setitem__(
                "page_id",
                999999,
            ),
            lambda value: value["candidates"][0]["wikipedia_article"].__setitem__(
                "title",
                "Candidate 001 renamed article",
            ),
            lambda value: value["candidate_universe"].__setitem__(
                "count",
                99,
            ),
            lambda value: value["candidates"][1].__setitem__(
                "evidence_state",
                "observed",
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(self.payload)
                mutate(changed)
                self.assertNotEqual(
                    serialize_semantic_payload(self.payload),
                    serialize_semantic_payload(changed),
                )


class CandidateAttentionFrontendCompatibilityTests(unittest.TestCase):
    def test_loader_accepts_unavailable_v11_record(self):
        if not __import__("shutil").which("node"):
            self.skipTest("node is unavailable")
        payload = {
            "schema_version": "1.1",
            "period": {"data_as_of": "2026-08-06"},
            "candidates": [
                {
                    "candidate_id": "candidate-001",
                    "candidate_name": "Candidate 001",
                    "evidence_state": "unavailable_no_personal_article",
                    "wikipedia_article": None,
                    "daily_series": [],
                }
            ],
        }
        script = r"""
const fs = require("fs");
const vm = require("vm");
const context = { window: {} };
vm.runInNewContext(
  fs.readFileSync("assets/candidate-attention.js", "utf8"),
  context
);
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(
  JSON.stringify(context.window.France2027CandidateAttention.normalize(payload))
);
"""
        completed = subprocess.run(
            ["node", "-e", script],
            input=json.dumps(payload),
            cwd=ROOT,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout)["status"],
            "ready",
        )


if __name__ == "__main__":
    unittest.main()
