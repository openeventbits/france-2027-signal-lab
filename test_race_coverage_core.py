import copy
import json
import random
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import fetch_news_wire as news_wire
from fetch_news_wire import (
    build_race_attention_period,
    race_inheritance_hard_veto,
)
from news_scope import unanchored_presidential_context
from race_coverage import (
    build_story_clusters,
    publisher_story_exposures,
    qualify_race_coverage,
)


def record(
    identifier,
    headline,
    *,
    publisher="Publisher A",
    published_at="2026-08-12T10:00:00Z",
    candidates=None,
    direct=False,
    story_id=None,
):
    candidates = list(candidates or [])
    value = {
        "id": identifier,
        "headline": headline,
        "publisher": publisher,
        "published_at": published_at,
        "candidate_names": candidates,
        "candidates": candidates,
        "direct_qualification": (
            {"reason": "presidential_context", "matched_terms": ["2027"]}
            if direct
            else None
        ),
    }
    if story_id is not None:
        value["story_id"] = story_id
    return value


ANCHOR = (
    "Présidentielle 2027 : Gabriel Attal porte plainte après une opération "
    "d’ingérence russe visant le scrutin"
)
PEER = (
    "Gabriel Attal porte plainte après une opération d’ingérence russe "
    "visant le scrutin"
)


class StoryIdentityTests(unittest.TestCase):
    candidates = ["Gabriel Attal", "Édouard Philippe", "Marine Le Pen"]

    def mapping(self, records, candidates=None):
        return {
            item["id"]: cluster["story_id"]
            for cluster in build_story_clusters(
                records,
                candidates or self.candidates,
            )
            for item in cluster["records"]
        }

    def test_unrelated_inventory_addition_does_not_change_assignment(self):
        records = [record("a", ANCHOR), record("b", PEER, publisher="Publisher B")]
        before = self.mapping(records)
        after = self.mapping(records + [record("z", "Budget municipal et transports régionaux")])
        self.assertEqual({key: after[key] for key in before}, before)

    def test_candidate_order_does_not_change_story_identity(self):
        records = [record("a", ANCHOR), record("b", PEER)]
        self.assertEqual(
            self.mapping(records, self.candidates),
            self.mapping(records, list(reversed(self.candidates))),
        )

    def test_unrelated_candidate_record_does_not_change_story_identity(self):
        records = [record("a", ANCHOR), record("b", PEER)]
        before = self.mapping(records)
        unrelated = record(
            "u",
            "Édouard Philippe visite un port régional",
            candidates=["Édouard Philippe"],
        )
        after = self.mapping(records + [unrelated])
        self.assertEqual({key: after[key] for key in before}, before)

    def test_story_identity_is_deterministic_under_input_ordering(self):
        records = [
            record("a", ANCHOR),
            record("b", PEER, publisher="Publisher B"),
            record("c", "Réforme scolaire dans une commune rurale"),
        ]
        expected = self.mapping(records)
        for seed in range(10):
            shuffled = copy.deepcopy(records)
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(self.mapping(shuffled), expected)

    def test_complete_link_invariant_holds_for_every_story_pair(self):
        from race_coverage import candidate_name_tokens, story_match

        records = [record("a", ANCHOR), record("b", PEER)]
        tokens = candidate_name_tokens(self.candidates)
        for cluster in build_story_clusters(records, self.candidates):
            members = cluster["records"]
            for left_index, left in enumerate(members):
                for right in members[left_index + 1 :]:
                    self.assertIsNotNone(
                        story_match(left, right, global_candidate_tokens=tokens)
                    )


class QualificationTests(unittest.TestCase):
    candidates = ["Gabriel Attal", "Édouard Philippe", "Marine Le Pen"]

    def test_candidate_attribution_does_not_propagate(self):
        anchor = record("a", ANCHOR, candidates=["Gabriel Attal"], direct=True)
        peer = record("b", PEER, publisher="Publisher B")
        qualified = {item["id"]: item for item in qualify_race_coverage(
            [anchor, peer], self.candidates
        )}
        self.assertEqual(qualified["b"]["qualification"], "cluster_confirmed")
        self.assertEqual(qualified["b"]["qualification_anchor_id"], "a")
        self.assertEqual(qualified["b"]["candidate_names"], [])

    def test_promoted_record_cannot_propagate_qualification(self):
        common = "operation ingerence russe reseau"
        anchor = record(
            "a",
            f"{common} plainte judiciaire etrangere",
            candidates=["Gabriel Attal"],
            direct=True,
        )
        promoted = record(
            "b",
            f"{common} plainte judiciaire etrangere campagne numerique manipulation",
            candidates=["Gabriel Attal"],
        )
        chained = record(
            "c",
            f"{common} campagne numerique manipulation",
            candidates=["Gabriel Attal"],
        )
        qualified = {item["id"]: item for item in qualify_race_coverage(
            [anchor, promoted, chained], self.candidates
        )}
        self.assertIn("b", qualified)
        self.assertNotIn("c", qualified)

    def test_direct_set_is_preserved_and_provenance_sets_are_disjoint(self):
        direct = record("direct", ANCHOR, direct=True)
        peer = record("peer", PEER, publisher="Publisher B")
        unrelated = record("other", "Budget municipal et transports régionaux")
        qualified = qualify_race_coverage(
            [direct, peer, unrelated],
            self.candidates,
            hard_veto=lambda _record: True,
        )
        direct_ids = {
            item["id"] for item in qualified
            if item["qualification"] == "direct"
        }
        cluster_ids = {
            item["id"] for item in qualified
            if item["qualification"] == "cluster_confirmed"
        }
        self.assertEqual(direct_ids, {"direct"})
        self.assertTrue(direct_ids.isdisjoint(cluster_ids))
        self.assertEqual(
            {item["id"] for item in qualified},
            direct_ids | cluster_ids,
        )

    def test_candidate_free_routine_governance_peer_does_not_inherit(self):
        peer = record(
            "peer",
            "Comment, depuis l’Assemblée, La France insoumise se prépare à gouverner",
        )
        self.assertTrue(race_inheritance_hard_veto(peer))


class ProductionDirectParityTests(unittest.TestCase):
    root = Path(__file__).resolve().parent
    generated_at = datetime.fromisoformat("2026-08-14T12:01:14+00:00")

    @staticmethod
    def not_modified(url, **_kwargs):
        return news_wire.HttpFetchResult(
            success=True,
            not_modified=True,
            status_code=304,
            response_body=None,
            final_url=url,
            attempts=1,
            elapsed_ms=0,
            etag=None,
            last_modified=None,
            failure_category=None,
            failure_message=None,
            response_bytes=0,
            retry_after_used=False,
        )

    def test_phase1c_direct_ids_exactly_equal_race_core_direct_ids(self):
        inventory = json.loads(
            (self.root / "news_inventory.json").read_text(encoding="utf-8")
        )
        baseline_direct_ids = set()
        for stored in inventory["items"]:
            matches = stored["candidate_matches"]
            candidates = news_wire.candidate_names_from_matches(matches)
            classification = news_wire.classify_relevant_news(
                stored["headline"],
                stored.get("summary") or "",
                candidates,
                matches,
            )
            if classification is None:
                continue
            if unanchored_presidential_context(
                stored["headline"], stored.get("summary") or "", candidates
            ):
                continue
            if news_wire.is_static_entity_page(
                stored["headline"], stored.get("url") or "", candidates
            ):
                continue
            baseline_direct_ids.add(stored["id"])

        with patch(
            "fetch_news_wire.fetch_news_route",
            side_effect=self.not_modified,
        ), patch(
            "fetch_news_wire.parse_feed",
            side_effect=AssertionError("304 responses must not be parsed"),
        ):
            payload, retained = news_wire.build_wire(
                self.root / "polls.json",
                30,
                0,
                self.root / "news_inventory.json",
                generated_at=self.generated_at,
            )

        direct_ids = {
            item["id"] for item in payload["relevant_news"]
            if item["qualification"] == "direct"
        }
        cluster_ids = {
            item["id"] for item in payload["relevant_news"]
            if item["qualification"] == "cluster_confirmed"
        }
        all_ids = {item["id"] for item in payload["relevant_news"]}
        self.assertTrue(retained["items"])
        self.assertTrue(baseline_direct_ids)
        self.assertEqual(direct_ids, baseline_direct_ids)
        self.assertTrue(direct_ids.isdisjoint(cluster_ids))
        self.assertEqual(all_ids, direct_ids | cluster_ids)
        self.assertNotIn("9bc07705527eaea340c7", cluster_ids)


class ExposureTests(unittest.TestCase):
    def coverage(self, identifier, publisher, story_id, candidates):
        return record(
            identifier,
            "headline",
            publisher=publisher,
            candidates=candidates,
            story_id=story_id,
        )

    def test_same_publisher_same_story_collapses_to_one_exposure(self):
        exposures = publisher_story_exposures([
            self.coverage("a", "P1", "s1", ["Gabriel Attal"]),
            self.coverage("b", "P1", "s1", ["Gabriel Attal"]),
        ])
        self.assertEqual(len(exposures), 1)
        self.assertEqual(exposures[0]["record_ids"], ["a", "b"])

    def test_different_publishers_remain_separate_exposures(self):
        exposures = publisher_story_exposures([
            self.coverage("a", "P1", "s1", ["Gabriel Attal"]),
            self.coverage("b", "P2", "s1", ["Gabriel Attal"]),
        ])
        self.assertEqual(len(exposures), 2)

    def test_multi_candidate_exposure_counts_once_in_denominator(self):
        period = build_race_attention_period(
            [self.coverage("a", "P1", "s1", ["Gabriel Attal", "Marine Le Pen"])],
            ["Gabriel Attal", "Marine Le Pen"],
            date(2026, 8, 8),
            date(2026, 8, 14),
        )
        self.assertEqual(period["exposure_count"], 1)
        self.assertEqual(
            {metric["candidate"]: metric["share"] for metric in period["candidate_metrics"]},
            {"Gabriel Attal": 1.0, "Marine Le Pen": 1.0},
        )

    def test_candidate_free_story_stays_out_of_denominator(self):
        period = build_race_attention_period(
            [self.coverage("a", "P1", "s1", [])],
            ["Gabriel Attal"],
            date(2026, 8, 8),
            date(2026, 8, 14),
        )
        self.assertEqual(period["record_count"], 1)
        self.assertEqual(period["exposure_count"], 0)

    def test_zero_candidate_receives_observed_zero(self):
        period = build_race_attention_period(
            [self.coverage("a", "P1", "s1", ["Gabriel Attal"])],
            ["Gabriel Attal", "Gérald Darmanin"],
            date(2026, 8, 8),
            date(2026, 8, 14),
        )
        metrics = {metric["candidate"]: metric for metric in period["candidate_metrics"]}
        self.assertEqual(metrics["Gérald Darmanin"]["observation_state"], "observed_zero")
        self.assertEqual(metrics["Gérald Darmanin"]["share"], 0.0)

    def test_unusable_denominator_produces_unavailable(self):
        period = build_race_attention_period(
            [],
            ["Gabriel Attal", "Gérald Darmanin"],
            date(2026, 8, 8),
            date(2026, 8, 14),
        )
        self.assertTrue(all(
            metric["observation_state"] == "unavailable"
            and metric["share"] is None
            for metric in period["candidate_metrics"]
        ))


if __name__ == "__main__":
    unittest.main()
