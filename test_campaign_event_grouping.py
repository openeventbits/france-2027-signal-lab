"""Frozen incident conservation and semantic campaign occurrence contracts."""
import copy
import itertools
import json
import random
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import generate_recent_changes as ledger
from campaign_event_identity import launch_identity, validate_occurrences

ROOT = Path(__file__).resolve().parent
FIXTURE = json.loads((ROOT / "tests/fixtures/campaign_launch_20261025.json").read_text(encoding="utf-8"))
CLOCK = ledger.parse_datetime(FIXTURE["checked_at"])


def article(key, headline, published="2026-10-25T18:00:00Z", candidates=("Marine Le Pen",)):
    return {"id": key, "headline": headline, "publisher": "Publisher " + key,
            "published_at": published, "url": "https://example.test/" + key,
            "candidates": list(candidates), "summary": "", "explicit_election": True}


def entries(rows, prior=None):
    return ledger.news_entries({"generated_at": FIXTURE["checked_at"], "election_news": rows,
                               "notable_developments": [], "candidate_watch": []},
                              prior or {}, CLOCK, Counter())


def sources(items):
    result = []
    for item in items:
        result.append((item["primary_source"]["name"], item["primary_source"]["url"], item["published_at"]))
        result.extend((s["name"], s["url"], s["published_at"]) for s in item["supporting_sources"])
    return Counter(result)


def compose(rows, previous):
    return ledger.compose_recent_changes(
        news={"generated_at": FIXTURE["checked_at"], "election_news": rows,
              "notable_developments": [], "candidate_watch": []},
        polls=[], runoff={"status": "insufficient"}, second_round={"events": []},
        claims={"reviews": []}, previous=previous, checked_at=CLOCK,
    )


class CampaignEventGroupingTests(unittest.TestCase):
    def test_frozen_incident_contains_all_original_records(self):
        self.assertEqual(len(FIXTURE["items"]), 18)
        self.assertEqual(sum(i["supporting_source_count"] for i in FIXTURE["items"]), 6)
        self.assertEqual(len(FIXTURE["news_rows"]), 24)
        self.assertEqual(len(sources(FIXTURE["items"])), 24)
        self.assertEqual(len({s[0] for s in sources(FIXTURE["items"])}), 16)

    def test_incident_conserves_every_url_publisher_and_publication(self):
        before = copy.deepcopy(FIXTURE)
        prior = {i["id"]: i for i in FIXTURE["items"]}
        result = entries(FIXTURE["news_rows"], prior)
        self.assertEqual(sources(result), sources(FIXTURE["items"]))
        group = next(i for i in result if i["id"] == "campaign-ce9a329262e5cefe16d9")
        self.assertEqual(group["supporting_source_count"], 12)
        self.assertEqual(group["candidate_ids"], ["marine-le-pen"])
        self.assertEqual(group["event_date"], "2026-10-25")
        self.assertEqual(group["published_at"], "2026-10-25T16:39:08Z")
        self.assertEqual(group["trusted_change_at"], group["published_at"])
        self.assertEqual(group["trusted_change_date_kind"], "source_published")
        self.assertEqual(group["detected_at"], "2026-10-25T17:10:18.917790Z")
        self.assertEqual(FIXTURE, before)

    def test_previews_roundup_and_independent_developments_remain_separate(self):
        result = entries(FIXTURE["news_rows"], {i["id"]: i for i in FIXTURE["items"]})
        by_id = {i["id"]: i for i in result}
        separate = ["807a34f2598dc71a6dad", "46afbbd26685a6ea0e66", "eb183f480c8360cf538e",
                    "68814d7b18df6da546ab", "c71621765ccacffe888b", "4f009b1b2f9195759308"]
        for key in separate:
            with self.subTest(key=key):
                item = by_id["campaign-" + key]
                self.assertIsNone(item["event_date"])
                self.assertEqual(item["supporting_sources"], [])
        for key in ["807a34f2598dc71a6dad", "46afbbd26685a6ea0e66", "eb183f480c8360cf538e"]:
            self.assertEqual(by_id["campaign-" + key]["summary"], ledger.PREVIEW_SUMMARY)
        roundup = by_id["campaign-4f009b1b2f9195759308"]
        self.assertEqual(set(roundup["candidate_ids"]), {"marine-le-pen", "raphael-glucksmann"})
        self.assertNotIn("raphael-glucksmann", by_id["campaign-ce9a329262e5cefe16d9"]["candidate_ids"])

    def test_unanchored_reports_are_not_forced_into_known_occurrence(self):
        result = entries(FIXTURE["news_rows"])
        for key in ["da89e8a6d9e8fefbd116", "08b762f2068c545b90d2", "1e92b8db7b2503692fdc",
                    "48860f77a5fa5c1f05c7", "a40032ecef93209c2883"]:
            self.assertIn("campaign-" + key, {i["id"] for i in result})

    def test_incident_order_independence_and_corrected_prior_replay(self):
        prior = {i["id"]: copy.deepcopy(i) for i in FIXTURE["items"]}
        rows = copy.deepcopy(FIXTURE["news_rows"])
        expected = compose(rows, prior)
        for seed in range(8):
            random.Random(seed).shuffle(rows)
            self.assertEqual(compose(rows, prior), expected)
        replay = compose(rows, {i["id"]: i for i in expected["items"]})
        serialize = lambda p: json.dumps(p, ensure_ascii=False, indent=2) + "\n"
        self.assertEqual(serialize(expected), serialize(replay))

    def test_same_event_paraphrases_and_bounded_recap(self):
        rows = [article("a", "À Orléans, Marine Le Pen lance sa campagne"),
                article("b", "Marine Le Pen se lance dans la course à l'Élysée à Orléans", "2026-10-25T19:00:00Z"),
                article("c", "Depuis Orléans, Marine Le Pen a lancé sa campagne présidentielle", "2026-10-26T10:00:00Z")]
        grouped = entries(rows)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["id"], "campaign-a")
        self.assertEqual(grouped[0]["supporting_source_count"], 2)

    def test_same_candidate_action_without_occurrence_identity_is_insufficient(self):
        rows = [article("a", "Marine Le Pen lance sa campagne à Orléans"),
                article("b", "Marine Le Pen lance sa campagne sous haute pression")]
        self.assertEqual(len(entries(rows)), 2)

    def test_negative_launch_cases_cannot_fall_back_to_fuzzy_similarity(self):
        base = article("base", "Marine Le Pen lance sa campagne à Orléans")
        cases = [
            article("preview", "Marine Le Pen lance sa campagne à Orléans", "2026-10-24T18:00:00Z"),
            article("morning", "Marine Le Pen lance sa campagne à Orléans", "2026-10-25T09:00:00Z"),
            article("late", "Marine Le Pen lance sa campagne à Orléans", "2026-10-28T09:00:00Z"),
            article("place", "Marine Le Pen lance sa campagne à Lyon"),
            article("two-places", "À Paris, Marine Le Pen lance sa campagne après Orléans"),
            article("date", "Le 26 octobre 2026, Marine Le Pen lance sa campagne à Orléans"),
            article("iso-date", "Marine Le Pen lance sa campagne à Orléans le 2026-10-26"),
            article("weekday", "Ce lundi, Marine Le Pen lance sa campagne à Orléans", "2026-10-26T09:00:00Z"),
            article("actor", "À Orléans, Gabriel Attal lance sa campagne", candidates=["Gabriel Attal"]),
            article("dual", "Marine Le Pen réorganise son parti et lance sa campagne à Orléans"),
            article("nomination", "Marine Le Pen lance sa campagne à Orléans et nomme son directeur"),
            article("selection", "Marine Le Pen lance sa campagne à Orléans et est investie par son parti"),
            article("another-meeting", "Marine Le Pen lance sa campagne à Orléans lors d'un second meeting"),
            article("partial-name", "Marine Le Penelope lance sa campagne à Orléans"),
            article("future", "Marine Le Pen lance sa campagne à Orléans demain"),
            article("committee", "Marine Le Pen lance sa campagne à Orléans, un comité de soutien se forme"),
            article("roundup", "Marine Le Pen lance sa campagne à Orléans : le point sur la semaine"),
        ]
        for other in cases:
            with self.subTest(key=other["id"]):
                # Use atomic entry construction, avoiding the unique-headline
                # public validator when two deliberately conflicting titles match.
                left, right = entries([base])[0], entries([other])[0]
                self.assertFalse(ledger.news_entries_match(left, right))

    def test_summary_and_upstream_flag_cannot_supply_missing_place(self):
        row = article("unlocated", "Marine Le Pen lance sa campagne")
        row["summary"] = "À Orléans, la candidate a tenu son meeting le 25 octobre 2026."
        row["explicit_election"] = True
        self.assertIsNone(launch_identity(entries([row])[0], ledger.CAMPAIGN_OCCURRENCES))

    def test_summary_only_candidate_associations_cannot_contaminate_group(self):
        row = article("extra", "Marine Le Pen lance sa campagne à Orléans",
                      candidates=["Marine Le Pen", "Raphaël Glucksmann"])
        item = entries([row])[0]
        self.assertIsNone(launch_identity(item, ledger.CAMPAIGN_OCCURRENCES))

    def test_generalizes_to_other_actor_place_and_midnight_occurrence(self):
        occurrence = {"actor_id": "gabriel-attal", "actor_name": "Gabriel Attal",
                      "action": "campaign_launch", "place": "Lyon", "event_date": "2026-10-25",
                      "scheduled_start_at": "2026-10-25T23:30:00+01:00",
                      "evidence_urls": ["https://example.test/confirmed-event"]}
        with patch.object(ledger, "CAMPAIGN_OCCURRENCES", [occurrence]):
            rows = [article("midnight-a", "À Lyon, Gabriel Attal lance sa campagne", "2026-10-25T22:45:00Z", ["Gabriel Attal"]),
                    article("midnight-b", "Gabriel Attal se lance dans la course à l'Élysée à Lyon", "2026-10-25T23:15:00Z", ["Gabriel Attal"])]
            result = entries(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["event_date"], "2026-10-25")
        self.assertEqual(result[0]["published_at"], "2026-10-25T22:45:00Z")

    def test_multiple_possible_occurrences_fail_closed(self):
        first = copy.deepcopy(ledger.CAMPAIGN_OCCURRENCES[0])
        second = dict(first, event_date="2026-10-26", scheduled_start_at="2026-10-26T10:00:00+01:00")
        item = entries([article("ambiguous", "Marine Le Pen lance sa campagne à Orléans", "2026-10-26T12:00:00Z")])[0]
        item["event_date"] = None
        self.assertIsNone(launch_identity(item, [first, second]))

    def test_actual_scheduled_announcement_is_kept_as_its_own_development(self):
        row = article("announcement", "Présidentielle : Gabriel Attal annonce un meeting à Lyon pour novembre",
                      candidates=["Gabriel Attal"])
        result = entries([row])
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["event_date"])

    def test_two_articles_from_one_publisher_are_two_source_articles(self):
        rows = [article("one", "Marine Le Pen lance sa campagne à Orléans"),
                article("two", "À Orléans, Marine Le Pen lance sa campagne", "2026-10-25T19:00:00Z")]
        rows[0]["publisher"] = rows[1]["publisher"] = "Same publisher"
        result = entries(rows)[0]
        self.assertEqual(result["supporting_source_count"], 1)
        self.assertIn("1 additional source link documents", result["summary"])
        self.assertEqual(len(sources([result])), 2)

    def test_complete_link_prevents_transitive_bridge_and_is_order_independent(self):
        raw = entries([article(str(i), "À Lyon, Personne Source lance sa campagne " + str(i),
                               candidates=["Personne Source"]) for i in range(3)])
        # Build three distinct already-valid atomic entries; A~B and B~C but
        # A!~C. Single-link would collapse all three into one development.
        if len(raw) != 3:
            raw = [entries([article(str(i), "À Lyon, Personne Source lance sa campagne " + str(i),
                                    candidates=["Personne Source"])])[0] for i in range(3)]
        def match(a, b):
            return abs(int(a["id"].split("-")[-1]) - int(b["id"].split("-")[-1])) <= 1
        with patch.object(ledger, "news_entries_match", side_effect=match):
            expected = ledger.cluster_news_entries(raw)
            self.assertEqual(len(expected), 2)
            for order in itertools.permutations(raw):
                self.assertEqual(ledger.cluster_news_entries(list(order)), expected)

    def test_primary_ties_and_earliest_valid_detection_are_deterministic(self):
        rows = [article("a", "Marine Le Pen lance sa campagne à Orléans"),
                article("b", "À Orléans, Marine Le Pen lance sa campagne")]
        prior = {"campaign-a": {"detected_at": "2026-10-25T20:00:00Z"},
                 "campaign-b": {"detected_at": "2026-10-25T19:00:00Z"}}
        result = entries(rows, prior)[0]
        self.assertEqual(result["id"], "campaign-a")
        self.assertEqual(result["detected_at"], "2026-10-25T19:00:00Z")
        prior["campaign-b"]["detected_at"] = "2026-10-24T01:00:00Z"
        self.assertEqual(entries(rows, prior)[0]["detected_at"], "2026-10-25T20:00:00Z")

    def test_registry_rejects_duplicates_and_unreviewed_shape(self):
        row = copy.deepcopy(ledger.CAMPAIGN_OCCURRENCES[0])
        for rows in [[row, row], [dict(row, article_urls=["https://example.test/allowlist"])],
                     [dict(row, evidence_urls=[])], [dict(row, scheduled_start_at="unknown")],
                     [dict(row, event_date="2026-02-30")]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validate_occurrences({"schema_version": 1, "occurrences": rows})

    def test_static_bilingual_snapshot_exposes_all_support_links(self):
        from build_search_entrypoints import _render_change_item
        from lxml import html
        group = next(i for i in entries(FIXTURE["news_rows"])
                     if i["id"] == "campaign-ce9a329262e5cefe16d9")
        for language in ["fr", "en"]:
            document = html.fromstring(_render_change_item(group, language))
            self.assertEqual(document.xpath('.//details//a/@href'),
                             [s["url"] for s in group["supporting_sources"]])
            self.assertEqual(document.xpath('.//details//a/@title'),
                             [s["published_at"] for s in group["supporting_sources"]])
            self.assertTrue(document.xpath('.//details/summary'))


if __name__ == "__main__":
    unittest.main()
