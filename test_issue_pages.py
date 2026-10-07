from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
import re
import unittest

import build_issue_pages as builder
from candidate_page_contract import project_candidate_route_index
from issue_page_contract import (
    CANONICAL_ISSUE_IDS,
    IssuePageContractError,
    issue_manifest_payload,
    project_issue_pages,
    validate_issue_manifest,
)


ROOT = Path(__file__).resolve().parent


class IssuePageProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.news = json.loads((ROOT / "news_wire.json").read_text(encoding="utf-8"))
        cls.history = json.loads(
            (ROOT / "candidate_agenda_history.json").read_text(encoding="utf-8")
        )
        cls.coverage_history = json.loads(
            (ROOT / "issue_coverage_history.json").read_text(encoding="utf-8")
        )
        candidate_registry = json.loads(
            (ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8")
        )
        cls.candidate_index = project_candidate_route_index(candidate_registry, ROOT)
        cls.projection = project_issue_pages(
            cls.news,
            cls.history,
            candidate_routes=cls.candidate_index["candidates"],
            coverage_history=cls.coverage_history,
        )

    @staticmethod
    def _weaken_current(news, issue_id):
        topic = next(item for item in news["policy_agenda"]["topics"] if item["id"] == issue_id)
        series = next(
            item
            for item in news["policy_agenda"]["evolution"]["topics"]
            if item["id"] == issue_id
        )
        topic["publisher_count"] = 0
        topic["publisher_names"] = []
        topic["source_day_count"] = 0
        topic["active_day_count"] = 0
        topic["candidate_counts"] = []
        topic["supporting_items"] = []
        topic["supporting_item_count"] = 0
        series["item_count"] = 0
        series["publisher_count"] = 0
        series["source_day_count"] = 0
        series["active_day_count"] = 0
        series["previous_source_day_count"] = 0
        series["latest_source_day_count"] = 0
        series["previous_incidence"] = 0.0
        series["latest_incidence"] = 0.0
        series["incidence_change_pp"] = 0.0
        for day in series["daily_activity"]:
            day["item_count"] = 0
            day["source_day_count"] = 0
            day["incidence"] = 0.0

    @staticmethod
    def _weaken_history(history, issue_id):
        for candidate in history["candidates"]:
            for day in candidate["daily_series"]:
                day["policy_counts"][issue_id] = 0

    def _precision_boundary_news(self):
        news = copy.deepcopy(self.news)
        evolution = news["policy_agenda"]["evolution"]
        previous_dates = [
            day["date"]
            for day in evolution["accepted_daily_activity"]
            if evolution["previous_start"] <= day["date"] <= evolution["previous_end"]
        ]
        latest_dates = [
            day["date"]
            for day in evolution["accepted_daily_activity"]
            if evolution["latest_start"] <= day["date"] <= evolution["latest_end"]
        ]
        self.assertEqual(len(previous_dates), 7)
        self.assertEqual(len(latest_dates), 7)

        accepted_counts = {
            **dict(zip(previous_dates, (44, 44, 44, 44, 43, 43, 43))),
            **dict(zip(latest_dates, (31, 31, 30, 30, 30, 30, 30))),
        }
        for day in evolution["accepted_daily_activity"]:
            if day["date"] in accepted_counts:
                day["source_day_count"] = accepted_counts[day["date"]]

        economy_counts = {
            **dict(zip(previous_dates, (2, 1, 3, 1, 1, 4, 0))),
            **dict(zip(latest_dates, (1, 0, 1, 4, 1, 4, 6))),
        }
        for topic in evolution["topics"]:
            for day in topic["daily_activity"]:
                accepted_count = next(
                    accepted["source_day_count"]
                    for accepted in evolution["accepted_daily_activity"]
                    if accepted["date"] == day["date"]
                )
                day["accepted_source_day_count"] = accepted_count
                if topic["id"] == "economy_public_finances" and day["date"] in economy_counts:
                    day["source_day_count"] = economy_counts[day["date"]]
                    day["item_count"] = max(day["item_count"], day["source_day_count"])
                day["incidence"] = (
                    round(day["source_day_count"] / accepted_count, 6)
                    if accepted_count
                    else 0.0
                )

            topic["item_count"] = sum(
                day["item_count"] for day in topic["daily_activity"]
            )
            previous_count = sum(
                day["source_day_count"]
                for day in topic["daily_activity"]
                if evolution["previous_start"]
                <= day["date"]
                <= evolution["previous_end"]
            )
            latest_count = sum(
                day["source_day_count"]
                for day in topic["daily_activity"]
                if evolution["latest_start"] <= day["date"] <= evolution["latest_end"]
            )
            topic["previous_source_day_count"] = previous_count
            topic["latest_source_day_count"] = latest_count
            raw_previous = previous_count / 305
            raw_latest = latest_count / 212
            topic["previous_incidence"] = round(raw_previous, 6)
            topic["latest_incidence"] = round(raw_latest, 6)
            topic["incidence_change_pp"] = round(
                (raw_latest - raw_previous) * 100,
                3,
            )

        return news

    def test_all_canonical_roots_qualify_and_are_current(self):
        self.assertEqual(
            {issue["issue_id"] for issue in self.projection["issues"]},
            set(CANONICAL_ISSUE_IDS),
        )
        self.assertTrue(
            all(issue["lifecycle"] == "current" for issue in self.projection["issues"])
        )
        self.assertTrue(
            all(issue["qualification"]["historical"] for issue in self.projection["issues"])
        )

    def test_current_publication_threshold_fails_closed(self):
        issue_id = CANONICAL_ISSUE_IDS[0]
        news = copy.deepcopy(self.news)
        history = copy.deepcopy(self.history)
        self._weaken_current(news, issue_id)
        self._weaken_history(history, issue_id)
        projection = project_issue_pages(news, history)
        self.assertNotIn(issue_id, {item["issue_id"] for item in projection["issues"]})

    def test_historical_threshold_publishes_separately(self):
        issue_id = CANONICAL_ISSUE_IDS[0]
        news = copy.deepcopy(self.news)
        history = copy.deepcopy(self.history)
        self._weaken_current(news, issue_id)
        self._weaken_history(history, issue_id)
        for candidate_index, candidate in enumerate(history["candidates"][:2]):
            for offset, day in enumerate(candidate["daily_series"][:3]):
                day["policy_counts"][issue_id] = 2 if candidate_index == 0 else 1
        projection = project_issue_pages(news, history)
        issue = next(item for item in projection["issues"] if item["issue_id"] == issue_id)
        self.assertEqual(issue["lifecycle"], "historical")
        self.assertFalse(issue["qualification"]["current"])
        self.assertTrue(issue["qualification"]["historical"])
        self.assertGreaterEqual(
            issue["historical_candidate_associations"]["association_count"], 8
        )

    def test_previously_published_weak_root_becomes_dormant(self):
        issue_id = CANONICAL_ISSUE_IDS[0]
        news = copy.deepcopy(self.news)
        history = copy.deepcopy(self.history)
        self._weaken_current(news, issue_id)
        self._weaken_history(history, issue_id)
        previous = {"pages": [{"issue_id": issue_id}]}
        projection = project_issue_pages(news, history, previous_manifest=previous)
        issue = next(item for item in projection["issues"] if item["issue_id"] == issue_id)
        self.assertEqual(issue["lifecycle"], "dormant")

    def test_missing_canonical_taxonomy_id_fails_closed(self):
        news = copy.deepcopy(self.news)
        news["policy_agenda"]["topics"].pop()
        with self.assertRaises(IssuePageContractError):
            project_issue_pages(news, self.history)

    def test_coverage_series_is_actual_issue_volume_and_not_history(self):
        source_series = {
            item["id"]: item
            for item in self.news["policy_agenda"]["evolution"]["topics"]
        }
        for issue in self.projection["issues"]:
            projected = issue["current_coverage"]["evolution_30d"]
            source = source_series[issue["issue_id"]]["daily_activity"]
            self.assertEqual(
                [item["item_count"] for item in projected],
                [item["item_count"] for item in source],
            )
            self.assertEqual(len(projected), 30)
            self.assertEqual(
                issue["current_coverage"]["item_count"],
                sum(item["item_count"] for item in projected),
            )
            self.assertIsNot(
                issue["current_coverage"]["evolution_30d"],
                issue["historical_candidate_associations"]["daily"],
            )

    def test_current_week_comparison_preserves_policy_incidence_contract(self):
        source = {
            item["id"]: item
            for item in self.news["policy_agenda"]["evolution"]["topics"]
        }
        evolution = self.news["policy_agenda"]["evolution"]

        for issue in self.projection["issues"]:
            projected = issue["current_coverage"]["comparison_7d"]
            canonical = source[issue["issue_id"]]

            self.assertEqual(projected["days"], evolution["comparison_days"])
            self.assertEqual(projected["previous_start"], evolution["previous_start"])
            self.assertEqual(projected["previous_end"], evolution["previous_end"])
            self.assertEqual(projected["latest_start"], evolution["latest_start"])
            self.assertEqual(projected["latest_end"], evolution["latest_end"])
            self.assertEqual(
                projected["previous_source_day_count"],
                canonical["previous_source_day_count"],
            )
            self.assertEqual(
                projected["latest_source_day_count"],
                canonical["latest_source_day_count"],
            )
            self.assertEqual(
                projected["previous_incidence"],
                canonical["previous_incidence"],
            )
            self.assertEqual(
                projected["latest_incidence"],
                canonical["latest_incidence"],
            )
            self.assertEqual(
                projected["incidence_change_pp"],
                canonical["incidence_change_pp"],
            )

    def test_current_week_incidence_uses_raw_ratio_precision(self):
        news = self._precision_boundary_news()
        evolution = news["policy_agenda"]["evolution"]
        economy = next(
            topic
            for topic in evolution["topics"]
            if topic["id"] == "economy_public_finances"
        )
        previous_denominator = sum(
            day["source_day_count"]
            for day in evolution["accepted_daily_activity"]
            if evolution["previous_start"] <= day["date"] <= evolution["previous_end"]
        )
        latest_denominator = sum(
            day["source_day_count"]
            for day in evolution["accepted_daily_activity"]
            if evolution["latest_start"] <= day["date"] <= evolution["latest_end"]
        )
        self.assertEqual(previous_denominator, 305)
        self.assertEqual(latest_denominator, 212)
        self.assertEqual(economy["previous_source_day_count"], 12)
        self.assertEqual(economy["latest_source_day_count"], 17)
        self.assertEqual(economy["previous_incidence"], 0.039344)
        self.assertEqual(economy["latest_incidence"], 0.080189)
        self.assertEqual(economy["incidence_change_pp"], 4.084)

        projection = project_issue_pages(news, self.history)
        projected = next(
            issue
            for issue in projection["issues"]
            if issue["issue_id"] == "economy_public_finances"
        )
        self.assertEqual(
            projected["current_coverage"]["comparison_7d"]["incidence_change_pp"],
            4.084,
        )

        economy["incidence_change_pp"] = 4.085
        with self.assertRaisesRegex(
            IssuePageContractError,
            "incidence change is inconsistent",
        ):
            project_issue_pages(news, self.history)

    def test_current_week_incidence_rejects_reconciliation_corruption(self):
        mutations = {
            "previous numerator": lambda evolution, economy: economy.__setitem__(
                "previous_source_day_count",
                13,
            ),
            "latest numerator": lambda evolution, economy: economy.__setitem__(
                "latest_source_day_count",
                18,
            ),
            "previous incidence": lambda evolution, economy: economy.__setitem__(
                "previous_incidence",
                0.039345,
            ),
            "latest incidence": lambda evolution, economy: economy.__setitem__(
                "latest_incidence",
                0.080188,
            ),
            "accepted denominator": self._increase_previous_denominator,
            "missing denominator series": lambda evolution, economy: evolution.pop(
                "accepted_daily_activity"
            ),
            "inconsistent window": lambda evolution, economy: evolution.__setitem__(
                "latest_end",
                evolution["period_end"],
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                news = self._precision_boundary_news()
                evolution = news["policy_agenda"]["evolution"]
                economy = next(
                    topic
                    for topic in evolution["topics"]
                    if topic["id"] == "economy_public_finances"
                )
                mutate(evolution, economy)
                with self.assertRaises(IssuePageContractError):
                    project_issue_pages(news, self.history)

    @staticmethod
    def _increase_previous_denominator(evolution, _economy):
        previous_start = evolution["previous_start"]
        accepted = next(
            day
            for day in evolution["accepted_daily_activity"]
            if day["date"] == previous_start
        )
        accepted["source_day_count"] += 1
        for topic in evolution["topics"]:
            day = next(
                observation
                for observation in topic["daily_activity"]
                if observation["date"] == previous_start
            )
            day["accepted_source_day_count"] += 1

    def test_campaign_agenda_projection_uses_complete_week_single_label_counts(self):
        summary = self.projection["campaign_agenda"]
        source = self.news["campaign_agenda"]["evolution"]
        self.assertEqual(
            summary["method"],
            "accepted_relevant_news_by_campaign_theme",
        )
        self.assertEqual(
            summary["metric"],
            "classified_campaign_agenda_item_share",
        )

        source_by_id = {item["id"]: item for item in source["topics"]}
        for topic in summary["topics"]:
            canonical = source_by_id[topic["id"]]
            previous = sum(
                day["item_count"]
                for day in canonical["daily_activity"]
                if source["previous_start"] <= day["date"] <= source["previous_end"]
            )
            latest = sum(
                day["item_count"]
                for day in canonical["daily_activity"]
                if source["latest_start"] <= day["date"] <= source["latest_end"]
            )
            self.assertEqual(topic["previous_item_count"], previous)
            self.assertEqual(topic["latest_item_count"], latest)

        self.assertEqual(
            summary["previous_total"],
            sum(item["previous_item_count"] for item in summary["topics"]),
        )
        self.assertEqual(
            summary["latest_total"],
            sum(item["latest_item_count"] for item in summary["topics"]),
        )
        if summary["previous_total"]:
            self.assertAlmostEqual(
                sum(item["previous_share"] for item in summary["topics"]),
                1.0,
                places=5,
            )
        if summary["latest_total"]:
            self.assertAlmostEqual(
                sum(item["latest_share"] for item in summary["topics"]),
                1.0,
                places=5,
            )

    def test_latest_observations_are_deduplicated_by_id_and_url(self):
        observations = self.projection["latest_observations"]
        self.assertEqual(
            len({item["id"] for item in observations}),
            len(observations),
        )
        self.assertEqual(
            len({item["url"] for item in observations}),
            len(observations),
        )
        canonical_order = {
            issue_id: index
            for index, issue_id in enumerate(CANONICAL_ISSUE_IDS)
        }
        for item in observations:
            self.assertTrue(item["issue_ids"])
            self.assertEqual(
                item["issue_ids"],
                sorted(item["issue_ids"], key=canonical_order.__getitem__),
            )

    def test_persistent_coverage_history_is_a_third_separate_domain(self):
        source_by_id = {
            issue["id"]: issue for issue in self.coverage_history["issues"]
        }
        for issue in self.projection["issues"]:
            self.assertEqual(
                issue["coverage_history"]["daily"],
                source_by_id[issue["issue_id"]]["daily"],
            )
            self.assertIsNot(
                issue["coverage_history"]["daily"],
                issue["current_coverage"]["evolution_30d"],
            )
            self.assertIsNot(
                issue["coverage_history"]["daily"],
                issue["historical_candidate_associations"]["daily"],
            )

    def test_source_fields_are_preserved_verbatim(self):
        source_topics = {
            item["id"]: item for item in self.news["policy_agenda"]["topics"]
        }
        for issue in self.projection["issues"]:
            expected = {
                item["id"]: (item["publisher"], item["headline"], item["url"])
                for item in source_topics[issue["issue_id"]]["supporting_items"]
            }
            for item in issue["evidence"]:
                self.assertEqual(
                    (item["publisher"], item["headline"], item["url"]),
                    expected[item["id"]],
                )

    def test_candidate_link_fallback_is_explicit(self):
        news = copy.deepcopy(self.news)
        topic = news["policy_agenda"]["topics"][0]
        topic["candidate_counts"].append(
            {"candidate": "Non-public fixture person", "item_count": 1}
        )
        projection = project_issue_pages(
            news,
            self.history,
            candidate_routes=self.candidate_index["candidates"],
        )
        projected_topic = next(
            item for item in projection["issues"] if item["issue_id"] == topic["id"]
        )
        fixture = next(
            item
            for item in projected_topic["current_candidate_associations"]["candidates"]
            if item["candidate_name"] == "Non-public fixture person"
        )
        self.assertIsNone(fixture["routes"])

    def test_related_issues_are_deterministic_observed_intersections(self):
        second = project_issue_pages(
            self.news,
            self.history,
            candidate_routes=self.candidate_index["candidates"],
        )
        self.assertEqual(
            [item["related_issues"] for item in self.projection["issues"]],
            [item["related_issues"] for item in second["issues"]],
        )
        evidence = {
            issue["issue_id"]: {item["id"] for item in issue["evidence"]}
            for issue in self.projection["issues"]
        }
        for issue in self.projection["issues"]:
            for related in issue["related_issues"]:
                self.assertEqual(
                    set(related["evidence_ids"]),
                    evidence[issue["issue_id"]] & evidence[related["issue_id"]],
                )
            self.assertLessEqual(len(issue["related_issues"]), 4)

    def test_subtopic_seam_has_no_phase_one_urls(self):
        for issue in self.projection["issues"]:
            counts = [item["item_count"] for item in issue["subtopics"]]
            self.assertEqual(counts, sorted(counts, reverse=True))
            for subtopic in issue["subtopics"]:
                self.assertFalse(subtopic["promotion"]["eligible"])
                self.assertIsNone(subtopic["promotion"]["route"])

    def test_no_event_poll_or_fact_check_relationship_input(self):
        implementation = inspect.getsource(project_issue_pages)
        for forbidden in ("polls.json", "campaign_events", "claims_under_scrutiny"):
            self.assertNotIn(forbidden, implementation)


class IssuePageArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(
            (ROOT / "issue_pages_manifest.json").read_text(encoding="utf-8")
        )
        validate_issue_manifest(cls.manifest)
        cls.hub_fr = (ROOT / "enjeux" / "index.html").read_text(encoding="utf-8")
        cls.hub_en = (ROOT / "en" / "issues" / "index.html").read_text(
            encoding="utf-8"
        )
        rendered = builder.build_from_paths(write=False)["artifacts"]
        cls.history_hub_fr = rendered[
            Path("enjeux/historique/index.html")
        ].decode("utf-8")
        cls.history_hub_en = rendered[
            Path("en/issues/history/index.html")
        ].decode("utf-8")
        cls.coverage_period = json.loads(
            (ROOT / "issue_coverage_history.json").read_text(encoding="utf-8")
        )["period"]


    def test_manifest_page_count_is_dynamic(self):
        self.assertEqual(
            self.manifest["issue_count"],
            len(self.manifest["pages"]),
        )
        self.assertEqual(self.manifest["issue_count"], 8)

        self.assertEqual(
            self.manifest["page_count"],
            len(self.manifest["pages"]) * 4 + 4,
        )
        self.assertEqual(self.manifest["page_count"], 36)

        self.assertEqual(
            self.manifest["history_hubs"],
            {
                "fr": "/enjeux/historique/",
                "en": "/en/issues/history/",
            },
        )

        for page in self.manifest["pages"]:
            self.assertIn(
                "history_page_path_fr",
                page,
            )
            self.assertIn(
                "history_page_path_en",
                page,
            )


    def test_hubs_have_five_metrics_and_static_links(self):
        for document in (self.hub_fr, self.hub_en):
            self.assertEqual(document.count('class="polling-metric"'), 4)
            self.assertEqual(document.count('class="polling-metric polling-metric-period"'), 1)
        for page in self.manifest["pages"]:
            self.assertIn(f'href="{page["page_path_fr"]}"', self.hub_fr)
            self.assertIn(f'href="{page["page_path_en"]}"', self.hub_en)

    def test_collection_and_item_list_jsonld(self):
        for document in (self.hub_fr, self.hub_en):
            payloads = [
                json.loads(value)
                for value in re.findall(
                    r'<script type="application/ld\+json">(.*?)</script>', document
                )
            ]
            collection = next(item for item in payloads if item.get("@type") == "CollectionPage")
            self.assertEqual(collection["mainEntity"]["@type"], "ItemList")
            self.assertEqual(
                collection["mainEntity"]["numberOfItems"],
                self.manifest["issue_count"],
            )

    def test_every_page_has_canonical_hreflang_and_no_null_leakage(self):
        paths = [ROOT / "enjeux" / "index.html", ROOT / "en" / "issues" / "index.html"]
        for page in self.manifest["pages"]:
            paths.extend(
                [
                    ROOT / page["page_path_fr"].strip("/") / "index.html",
                    ROOT / page["page_path_en"].strip("/") / "index.html",
                ]
            )
        for path in paths:
            document = path.read_text(encoding="utf-8")
            self.assertEqual(document.count('rel="canonical"'), 1)
            self.assertEqual(
                document.count('<link rel="alternate" hreflang="fr"'), 1
            )
            self.assertEqual(
                document.count('<link rel="alternate" hreflang="en"'), 1
            )
            self.assertEqual(
                document.count('<link rel="alternate" hreflang="x-default"'), 1
            )
            self.assertNotRegex(document, r">(?:None|null)<")
            self.assertIn('name="robots" content="index,follow,max-image-preview:large"', document)

    def test_detail_semantic_boundary_and_separate_history(self):
        page = self.manifest["pages"][0]
        rendered = builder.build_from_paths(write=False)["artifacts"]
        french = rendered[
            Path(page["page_path_fr"].strip("/")) / "index.html"
        ].decode("utf-8")
        english = rendered[
            Path(page["page_path_en"].strip("/")) / "index.html"
        ].decode("utf-8")
        self.assertIn('aria-label="Note de co-occurrence"', french)
        self.assertIn('aria-label="Co-occurrence note"', english)
        self.assertIn('id="issue-candidate-cooccurrence-note" role="tooltip"', french)
        self.assertIn('id="issue-candidate-cooccurrence-note" role="tooltip"', english)
        self.assertIn("ni position politique", french)
        self.assertIn("programme or manifesto commitment", english)
        self.assertIn("HISTORIQUE COMPACT", french)
        self.assertIn("COMPACT HISTORY", english)
        self.assertNotIn("HISTORIQUE DES ASSOCIATIONS CANDIDAT", french)
        self.assertNotIn("CANDIDATE × ISSUE ASSOCIATION HISTORY", english)


    def test_hub_history_gateway_follows_latest_observations(self):
        self.assertIn("HISTORIQUE DES ENJEUX", self.hub_fr)
        self.assertIn("ISSUE HISTORY", self.hub_en)
        self.assertIn('href="/enjeux/historique/"', self.hub_fr)
        self.assertIn('href="/en/issues/history/"', self.hub_en)
        self.assertLess(
            self.hub_fr.index("DERNIÈRES OBSERVATIONS SOURCÉES"),
            self.hub_fr.index("HISTORIQUE DES ENJEUX"),
        )
        self.assertLess(
            self.hub_en.index("LATEST SOURCE-LINKED OBSERVATIONS"),
            self.hub_en.index("ISSUE HISTORY"),
        )

    def test_historical_hub_uses_only_historical_coverage_semantics(self):
        for document, assignment, corpus, window in (
            (self.history_hub_fr, "ASSIGNATIONS D’ENJEU", "ARTICLES · CORPUS", "28 J"),
            (self.history_hub_en, "ISSUE ASSIGNMENTS", "CORPUS ITEMS", "28D"),
        ):
            self.assertIn(assignment, document)
            self.assertIn(corpus, document)
            self.assertIn(window, document)
            self.assertNotIn("CANDIDATS ASSOCIÉS", document)
            self.assertNotIn("ASSOCIATED CANDIDATES", document)
            self.assertNotIn("SINGLE-LABEL", document)
            self.assertNotIn("ÉTIQUETTE UNIQUE", document)
        self.assertIn("Activité = incidence des 28 derniers", self.history_hub_fr)
        self.assertIn("Movement = absolute change", self.history_hub_en)
        self.assertIn(
            "ARTICLES DISTINCTS · 30 J",
            self.hub_fr,
        )

        self.assertIn(
            "DISTINCT ITEMS · 30D",
            self.hub_en,
        )


    def test_hub_landscape_search_sort_and_bounded_source_evidence(self):
        self.assertIn("PAYSAGE DES ENJEUX", self.hub_fr)
        self.assertIn("ISSUE LANDSCAPE", self.hub_en)
        for document in (self.hub_fr, self.hub_en):
            self.assertIn('id="issue-search"', document)
            self.assertEqual(document.count("data-issue-sort="), 4)
            self.assertIn('data-issue-sort="activity" aria-pressed="true"', document)
            self.assertEqual(
                document.count('class="issue-evidence-row issue-hub-evidence-row"'),
                6,
            )
            self.assertEqual(
                document.count('class="issue-evidence-external"'),
                6,
            )
            self.assertGreaterEqual(
                document.count('class="issue-evidence-issue"'),
                6,
            )
            self.assertNotIn("issue-evidence-archive", document)

    def test_hub_has_exactly_eight_static_issue_cards_per_language(self):
        fr_cards = re.findall(
            r'<a\s+class="issue-card"\s+href="([^"]+)"',
            self.hub_fr,
        )
        en_cards = re.findall(
            r'<a\s+class="issue-card"\s+href="([^"]+)"',
            self.hub_en,
        )
        self.assertEqual(len(fr_cards), 8)
        self.assertEqual(len(en_cards), 8)
        self.assertEqual(
            set(fr_cards),
            {page["page_path_fr"] for page in self.manifest["pages"]},
        )
        self.assertEqual(
            set(en_cards),
            {page["page_path_en"] for page in self.manifest["pages"]},
        )

    def test_artifact_fixture_remains_disk_backed(self):
        source = inspect.getsource(
            IssuePageArtifactTests.setUpClass.__func__
        )
        self.assertIn('ROOT / "enjeux" / "index.html"', source)
        self.assertIn('ROOT / "en" / "issues" / "index.html"', source)
        self.assertLess(
            source.index('ROOT / "en" / "issues" / "index.html"'),
            source.index("build_from_paths"),
        )

    def test_historical_hub_javascript_has_no_dead_legacy_dependencies(self):
        script = (ROOT / "assets" / "issues.js").read_text(encoding="utf-8")
        for selector in (
            '[data-issue-list] [data-issue-row]',
            '[data-issue-select]',
            '[data-issue-directory] [data-issue-row]',
            '#issue-inspector-content',
        ):
            self.assertNotIn(selector, script)

        self.assertIn('document.querySelector("[data-issue-card-grid]")', script)
        self.assertIn("if (grid) {", script)
        self.assertIn('document.querySelectorAll("[data-history-panel]")', script)
        self.assertIn('panel.querySelectorAll("[data-history-mode]")', script)
        self.assertIn('panel.querySelectorAll("[data-history-series]")', script)

    def test_latest_evidence_has_static_issue_and_external_source_links(self):
        for document in (self.hub_fr, self.hub_en):
            latest = document.split(
                '<section class="polling-section issues-latest"',
                1,
            )[1].split(
                '<section class="polling-section issue-history-gateway',
                1,
            )[0]
            self.assertEqual(
                latest.count('class="issue-evidence-row issue-hub-evidence-row"'),
                6,
            )
            self.assertGreaterEqual(
                latest.count('class="issue-evidence-issue" href="'),
                6,
            )
            self.assertEqual(latest.count('target="_blank"'), 6)

    def test_hub_uses_compact_landscape_comparison_evidence_history_sequence(self):
        cases = (
            (
                self.hub_fr,
                "PAYSAGE DES ENJEUX",
                "CE QUI BOUGE",
                "AGENDA DE CAMPAGNE",
                "DERNIÈRES OBSERVATIONS SOURCÉES",
                "HISTORIQUE DES ENJEUX",
            ),
            (
                self.hub_en,
                "ISSUE LANDSCAPE",
                "WHAT’S MOVING",
                "CAMPAIGN AGENDA",
                "LATEST SOURCE-LINKED OBSERVATIONS",
                "ISSUE HISTORY",
            ),
        )

        for document, landscape, movement, agenda, latest, history in cases:
            self.assertIn("issue-card-grid", document)
            self.assertIn("issue-dumbbell", document)
            self.assertIn("issue-agenda-composition", document)
            self.assertNotIn("issue-evolution-matrix", document)
            self.assertNotIn("DOSSIER ENJEU", document)
            self.assertNotIn("ISSUE DOSSIER", document)
            self.assertNotIn("RÉPERTOIRE DES ENJEUX", document)
            self.assertNotIn("ISSUE DIRECTORY", document)
            self.assertNotIn("issues-monitor-panel", document)
            self.assertLess(document.index(landscape), document.index(movement))
            self.assertLess(document.index(movement), document.index(agenda))
            self.assertLess(document.index(agenda), document.index(latest))
            self.assertLess(document.index(latest), document.index(history))

    def test_current_hub_method_notes_use_polling_title_tooltips(self):
        cases = (
            (
                self.hub_fr,
                "issues-movement-note",
                "issues-agenda-note",
                "Incidence = jours-sources de l’enjeu",
                "Chaque article classé dans l’Agenda de campagne",
            ),
            (
                self.hub_en,
                "issues-movement-note",
                "issues-agenda-note",
                "Incidence = issue source-days",
                "Each article classified into Campaign Agenda",
            ),
        )

        for document, movement_id, agenda_id, movement_text, agenda_text in cases:
            self.assertNotIn('class="issue-comparison-note"', document)
            self.assertIn('class="polling-title-info"', document)
            self.assertIn('class="polling-title-tooltip"', document)
            self.assertIn(f'aria-describedby="{movement_id}"', document)
            self.assertIn(f'aria-describedby="{agenda_id}"', document)
            self.assertIn(f'id="{movement_id}" role="tooltip"', document)
            self.assertIn(f'id="{agenda_id}" role="tooltip"', document)
            self.assertIn(movement_text, document)
            self.assertIn(agenda_text, document)

    def test_current_hub_legend_uses_atomic_visible_items(self):
        for document in (self.hub_fr, self.hub_en):
            legend = document.split(
                '<div class="issue-dumbbell-legend"',
                1,
            )[1].split("</div>", 1)[0]
            self.assertEqual(
                legend.count('class="issue-dumbbell-legend-item"'),
                2,
            )
            self.assertEqual(len(re.findall(r"<small\b[^>]*>", legend)), 2)
            self.assertNotIn("title=", legend)

    def test_current_hub_responsive_css_has_one_ordered_contract(self):
        stylesheet = (ROOT / "assets" / "issues.css").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(".issue-dumbbell-legend > span", stylesheet)
        self.assertEqual(
            stylesheet.count("FR27 Issues current-hub responsive contract"),
            1,
        )
        responsive = stylesheet.split(
            "FR27 Issues current-hub responsive contract",
            1,
        )[1]
        for breakpoint in (
            "@media (min-width: 1000px)",
            "@media (max-width: 1349px)",
            "@media (max-width: 999px)",
            "@media (max-width: 759px)",
            "@media (max-width: 659px)",
            "@media (max-width: 479px)",
        ):
            self.assertEqual(responsive.count(breakpoint), 1)
        self.assertIn(
            ".issues-hub-page .issues-comparison-grid",
            responsive,
        )
        self.assertIn(
            "grid-template-columns: minmax(0, 1fr);",
            responsive,
        )
        self.assertIn(
            ".issues-history-page .issue-card-microbars",
            stylesheet,
        )

    def test_hub_redesign_does_not_enter_detail_renderers(self):
        for renderer in (builder.render_detail, builder.render_history_detail):
            source = inspect.getsource(renderer)
            self.assertNotIn("issue-card-grid", source)
            self.assertNotIn("issue-dumbbell", source)
            self.assertNotIn("issue-agenda-composition", source)

    def test_current_and_history_hubs_share_the_structural_renderer(self):
        for renderer in (builder.render_hub, builder.render_history_hub):
            self.assertIn(
                "_render_issue_hub_document(",
                inspect.getsource(renderer),
            )
        shared = inspect.getsource(builder._render_issue_hub_document)
        for structural_class in (
            "issues-metrics",
            "issues-landscape-panel",
            "issue-card-grid",
            "issues-comparison-grid",
            "issues-latest",
            "issue-history-gateway",
        ):
            self.assertIn(structural_class, shared)

    def test_historical_hubs_have_eight_cards_no_obsolete_inspector(self):
        for document in (self.history_hub_fr, self.history_hub_en):
            self.assertEqual(document.count('class="issue-card"'), 8)
            self.assertEqual(document.count('data-issue-sort='), 4)
            self.assertEqual(
                document.count('class="issue-evidence-row issue-hub-evidence-row"'),
                6,
            )
            self.assertEqual(
                document.count('class="issue-evidence-external"'),
                6,
            )
            evidence_dates = re.findall(
                r'<time datetime="(\d{4}-\d{2}-\d{2})">',
                document.split('class="polling-section issues-latest"', 1)[1]
                .split('class="polling-section issue-history-gateway', 1)[0],
            )
            self.assertEqual(len(evidence_dates), 6)
            self.assertTrue(
                all(
                    self.coverage_period["start_date"]
                    <= value
                    <= self.coverage_period["end_date"]
                    for value in evidence_dates
                )
            )
            for obsolete in (
                "data-issue-list",
                "data-issue-row",
                "data-issue-select",
                "issue-inspector-content",
                "issues-monitor-panel",
                "issue-directory-list",
            ):
                self.assertNotIn(obsolete, document)

    def test_historical_gateway_returns_to_current_hub(self):
        self.assertIn(
            'class="issue-history-gateway-cta" href="/enjeux/"',
            self.history_hub_fr,
        )
        self.assertIn(
            'class="issue-history-gateway-cta" href="/en/issues/"',
            self.history_hub_en,
        )

    def test_historical_hub_is_deterministic(self):
        first = builder.build_from_paths(write=False)["artifacts"]
        second = builder.build_from_paths(write=False)["artifacts"]
        for path in (
            Path("enjeux/historique/index.html"),
            Path("en/issues/history/index.html"),
        ):
            self.assertEqual(first[path], second[path])

    def test_historical_detail_pages_match_redesign_source_contract(self):
        rendered = builder.build_from_paths(write=False)["artifacts"]
        paths = []
        for page in self.manifest["pages"]:
            for route_key in (
                "history_page_path_fr",
                "history_page_path_en",
            ):
                paths.append(Path(page[route_key].strip("/")) / "index.html")
        for path in sorted(paths):
            self.assertEqual(
                rendered[path],
                (ROOT / path).read_text(encoding="utf-8").encode("utf-8"),
            )

    def test_current_hub_source_render_is_deterministic(self):
        first = builder.build_from_paths(write=False)["artifacts"]
        second = builder.build_from_paths(write=False)["artifacts"]
        for path in (
            Path("enjeux/index.html"),
            Path("en/issues/index.html"),
        ):
            self.assertEqual(first[path], second[path])

    def test_current_hub_html_remains_byte_identical(self):
        rendered = builder.build_from_paths(write=False)["artifacts"]
        for path in (
            Path("enjeux/index.html"),
            Path("en/issues/index.html"),
        ):
            self.assertEqual(
                rendered[path],
                (ROOT / path).read_text(encoding="utf-8").encode("utf-8"),
            )

    def test_historical_url_family_is_complete(self):
        import build_issue_pages as pages

        result = pages.build_from_paths(
            write=False,
        )

        self.assertEqual(
            result["manifest"]["page_count"],
            36,
        )

        self.assertEqual(
            len(result["artifacts"]),
            36,
        )

        self.assertIn(
            Path("enjeux/historique/index.html"),
            result["artifacts"],
        )

        self.assertIn(
            Path("en/issues/history/index.html"),
            result["artifacts"],
        )

        history_details = [
            path
            for path in result["artifacts"]
            if (
                path.as_posix().startswith(
                    "enjeux/historique/"
                )
                or path.as_posix().startswith(
                    "en/issues/history/"
                )
            )
            and path.name == "index.html"
            and path.as_posix()
            not in {
                "enjeux/historique/index.html",
                "en/issues/history/index.html",
            }
        ]

        self.assertEqual(
            len(history_details),
            16,
        )

        for page in result["manifest"]["pages"]:
            fr = (
                Path(
                    page[
                        "history_page_path_fr"
                    ].strip("/")
                )
                / "index.html"
            )

            en = (
                Path(
                    page[
                        "history_page_path_en"
                    ].strip("/")
                )
                / "index.html"
            )

            self.assertIn(
                fr,
                result["artifacts"],
            )

            self.assertIn(
                en,
                result["artifacts"],
            )

        history_fr = result["artifacts"][
            Path("enjeux/historique/index.html")
        ].decode("utf-8")

        history_en = result["artifacts"][
            Path("en/issues/history/index.html")
        ].decode("utf-8")

        self.assertIn(
            'rel="canonical" '
            'href="https://france2027.app/enjeux/historique/"',
            history_fr,
        )

        self.assertIn(
            'rel="canonical" '
            'href="https://france2027.app/en/issues/history/"',
            history_en,
        )

        self.assertIn(
            "PAYSAGE HISTORIQUE DES ENJEUX",
            history_fr,
        )

        self.assertIn(
            "HISTORICAL ISSUE LANDSCAPE",
            history_en,
        )

        self.assertIn(
            "CADENCE DE COUVERTURE",
            history_fr,
        )


    def test_rendering_is_deterministic(self):
        news = json.loads((ROOT / "news_wire.json").read_text(encoding="utf-8"))
        history = json.loads(
            (ROOT / "candidate_agenda_history.json").read_text(encoding="utf-8")
        )
        coverage_history = json.loads(
            (ROOT / "issue_coverage_history.json").read_text(encoding="utf-8")
        )
        candidate_registry = json.loads(
            (ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8")
        )
        routes = project_candidate_route_index(candidate_registry, ROOT)["candidates"]
        projection = project_issue_pages(
            news,
            history,
            previous_manifest=self.manifest,
            candidate_routes=routes,
            coverage_history=coverage_history,
        )
        templates = builder.load_shell_templates(ROOT)
        poll_manifest = json.loads(
            (ROOT / "poll_pages_manifest.json").read_text(encoding="utf-8")
        )
        for template in templates.values():
            template["footer"] = builder.prepare_footer(
                template["footer"], poll_manifest["wave_count"]
            )
        favicon = builder._site_favicon_link(ROOT)
        og_image = builder._site_og_image_url(ROOT)
        first = builder.render_hub(
            projection,
            language="fr",
            shell=templates["fr"],
            favicon=favicon,
            og_image=og_image,
        )
        second = builder.render_hub(
            projection,
            language="fr",
            shell=templates["fr"],
            favicon=favicon,
            og_image=og_image,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            (ROOT / "enjeux" / "index.html")
            .read_text(encoding="utf-8")
            .encode("utf-8"),
        )


class CurrentIssueDetailRedesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = builder.build_from_paths(write=False)
        cls.projection = cls.result["projection"]
        cls.artifacts = cls.result["artifacts"]
        cls.issues = cls.projection["issues"]

    @staticmethod
    def _path(issue, language, *, history=False):
        route = (
            builder._history_route(issue, language)
            if history
            else issue["routes"][language]
        )
        return Path(route.strip("/")) / "index.html"

    def _document(self, issue, language, *, history=False):
        return self.artifacts[
            self._path(issue, language, history=history)
        ].decode("utf-8")

    def test_current_detail_uses_projected_complete_week_incidence(self):
        for issue in self.issues:
            comparison = issue["current_coverage"]["comparison_7d"]
            for language in ("fr", "en"):
                document = self._document(issue, language)
                self.assertIn(
                    f'data-previous-incidence="{comparison["previous_incidence"]}"',
                    document,
                )
                self.assertIn(
                    f'data-latest-incidence="{comparison["latest_incidence"]}"',
                    document,
                )
                self.assertIn(
                    f'data-incidence-change-pp="{comparison["incidence_change_pp"]}"',
                    document,
                )
                self.assertIn(
                    builder._incidence_label(
                        comparison["previous_incidence"], language
                    ),
                    document,
                )
                self.assertIn(
                    builder._incidence_label(
                        comparison["latest_incidence"], language
                    ),
                    document,
                )

    def test_current_detail_subtopics_remain_overlapping_counts(self):
        for issue in self.issues:
            document = self._document(issue, "en")
            panel = document.split('aria-labelledby="subtopics-title"', 1)[1].split(
                "</section>", 1
            )[0]
            self.assertIn("Subtopics can overlap", panel)
            self.assertNotIn("ISSUE COMPOSITION", panel)
            for subtopic in issue["subtopics"]:
                self.assertIn(builder._h(subtopic["labels"]["en"]), panel)
                self.assertIn(f"<strong>{subtopic['item_count']}</strong>", panel)

    def test_current_detail_has_locked_module_sequence(self):
        cases = (
            (
                "fr",
                "ACTIVITÉ ACTUELLE",
                "SOUS-THÈMES OBSERVÉS",
                "ASSOCIATIONS ACTUELLES DE CANDIDATS",
                "DERNIÈRES PREUVES SOURCÉES",
                "HISTORIQUE COMPACT",
                "ENJEUX CO-OCCURRENTS",
            ),
            (
                "en",
                "CURRENT ACTIVITY",
                "OBSERVED SUBTOPICS",
                "CURRENT CANDIDATE ASSOCIATIONS",
                "LATEST SOURCE-LINKED EVIDENCE",
                "COMPACT HISTORY",
                "CO-OCCURRING ISSUES",
            ),
        )
        for language, *headings in cases:
            document = self._document(self.issues[0], language)
            positions = [document.index(heading) for heading in headings]
            self.assertEqual(positions, sorted(positions))

    def test_current_detail_does_not_render_full_historical_coverage_visual(self):
        for issue in self.issues:
            for language in ("fr", "en"):
                document = self._document(issue, language)
                self.assertNotIn("issue-detail-coverage-history", document)
                self.assertNotIn('data-history-mode="volume"', document)
                self.assertNotIn("CORPUS SHARE", document)
                self.assertNotIn("PART DU CORPUS", document)

    def test_current_detail_does_not_render_historical_candidate_association_archive(self):
        for issue in self.issues:
            for language in ("fr", "en"):
                document = self._document(issue, language)
                self.assertNotIn("HISTORIQUE DES ASSOCIATIONS CANDIDAT", document)
                self.assertNotIn("CANDIDATE × ISSUE ASSOCIATION HISTORY", document)
                self.assertNotIn("association-history-title", document)

    def test_historical_detail_still_owns_longitudinal_controls_and_candidate_history(self):
        french = self._document(self.issues[0], "fr", history=True)
        english = self._document(self.issues[0], "en", history=True)
        for document in (french, english):
            self.assertIn('data-history-mode="volume"', document)
            self.assertIn('data-history-mode="share"', document)
            self.assertIn("issue-history-daily", document)
        self.assertIn("HISTORIQUE DES ASSOCIATIONS CANDIDAT × ENJEU", french)
        self.assertIn("CANDIDATE × ISSUE ASSOCIATION HISTORY", english)

    def test_current_detail_activity_renders_one_mark_per_projection_day(self):
        for issue in self.issues:
            document = self._document(issue, "fr")
            expected = len(issue["current_coverage"]["evolution_30d"])
            self.assertEqual(
                document.count('class="issue-detail-activity-bar '),
                expected,
            )
            self.assertIn(
                f"--issue-activity-columns:{expected}",
                document,
            )

    def test_current_detail_activity_marks_complete_week_windows(self):
        for issue in self.issues:
            comparison = issue["current_coverage"]["comparison_7d"]
            document = self._document(issue, "en")
            for point in issue["current_coverage"]["evolution_30d"]:
                if comparison["previous_start"] <= point["date"] <= comparison["previous_end"]:
                    expected = "is-previous"
                elif comparison["latest_start"] <= point["date"] <= comparison["latest_end"]:
                    expected = "is-latest"
                elif point["date"] > comparison["latest_end"]:
                    expected = "is-partial"
                else:
                    expected = "is-older"
                self.assertIn(
                    f'class="issue-detail-activity-bar {expected}" data-date="{point["date"]}"',
                    document,
                )

    def test_current_detail_candidate_module_preserves_explicit_cooccurrence_boundary(self):
        french = self._document(self.issues[0], "fr")
        english = self._document(self.issues[0], "en")
        for phrase in (
            "ni soutien",
            "ni opposition",
            "ni priorité",
            "ni idéologie",
            "ni position politique",
            "ni engagement de programme",
        ):
            self.assertIn(phrase, french)
        for phrase in (
            "support",
            "opposition",
            "priority",
            "ideology",
            "political position",
            "programme or manifesto commitment",
        ):
            self.assertIn(phrase, english)

    def test_current_detail_notes_use_accessible_tooltips(self):
        button_tooltip_ids = (
            "issue-incidence-method-note",
            "issue-subtopics-note",
            "issue-candidate-cooccurrence-note",
            "issue-related-evidence-note",
        )
        incidence_cell_tooltip_ids = (
            "issue-incidence-previous-dates",
            "issue-incidence-latest-dates",
        )
        tooltip_ids = button_tooltip_ids + incidence_cell_tooltip_ids

        for issue in self.issues:
            for language in ("fr", "en"):
                document = self._document(issue, language)

                self.assertNotIn('<details class="issue-note-tooltip', document)

                # Every contextual note remains explicitly associated with
                # an accessible tooltip, regardless of trigger type.
                for tooltip_id in tooltip_ids:
                    self.assertIn(
                        f'aria-describedby="{tooltip_id}"',
                        document,
                    )
                    self.assertIn(
                        f'id="{tooltip_id}" role="tooltip"',
                        document,
                    )

                # Methodological/context notes retain explicit info buttons.
                self.assertEqual(
                    document.count('class="issue-note-tooltip-trigger"'),
                    len(button_tooltip_ids),
                )

                # Complete-week date notes use the whole incidence metric
                # cell as the hover/focus target; no redundant visible "i".
                self.assertEqual(
                    document.count("issue-incidence-period"),
                    len(incidence_cell_tooltip_ids),
                )
                self.assertEqual(
                    document.count("issue-incidence-date-tooltip"),
                    len(incidence_cell_tooltip_ids),
                )
    def test_current_detail_tooltip_copy_is_bilingual_and_complete(self):
        french = self._document(self.issues[0], "fr")
        english = self._document(self.issues[0], "en")
        for phrase in (
            "Jours-sources de cet enjeu ÷ jours-sources de couverture présidentielle retenue.",
            "Les sous-thèmes peuvent se chevaucher ; les barres indiquent une magnitude relative et non des parts totalisant 100 %.",
            "Preuves publiées communes ; pas une similarité idéologique ou programmatique.",
        ):
            self.assertIn(phrase, french)
        for phrase in (
            "Source-days for this issue ÷ accepted presidential-coverage source-days.",
            "Subtopics can overlap; bars show relative magnitude, not shares that sum to 100%.",
            "Shared published evidence; not ideological or policy similarity.",
        ):
            self.assertIn(phrase, english)

    def test_current_detail_incidence_dates_live_only_in_value_tooltips(self):
        for issue in self.issues:
            comparison = issue["current_coverage"]["comparison_7d"]
            for language in ("fr", "en"):
                document = self._document(issue, language)
                comparison_markup = document.split(
                    '<dl class="issue-current-comparison">', 1
                )[1].split("</dl>", 1)[0]
                prefix = "Semaine complète" if language == "fr" else "Complete week"
                previous = builder._period(
                    comparison["previous_start"],
                    comparison["previous_end"],
                    language,
                )
                latest = builder._period(
                    comparison["latest_start"],
                    comparison["latest_end"],
                    language,
                )
                self.assertIn(
                    f'id="issue-incidence-previous-dates" role="tooltip">{prefix} · {previous}',
                    comparison_markup,
                )
                self.assertIn(
                    f'id="issue-incidence-latest-dates" role="tooltip">{prefix} · {latest}',
                    comparison_markup,
                )
                self.assertNotIn("<small>", comparison_markup)

    def test_current_detail_candidate_links_remain_static(self):
        issue = copy.deepcopy(self.issues[0])
        issue["current_candidate_associations"]["candidates"][0]["routes"] = None
        rows = builder._candidate_rows(issue, "en")
        self.assertNotIn("<button", rows)
        fallback = issue["current_candidate_associations"]["candidates"][0]
        self.assertIn(f"<span>{fallback['candidate_name']}</span>", rows)
        for candidate in issue["current_candidate_associations"]["candidates"][1:]:
            if candidate["routes"]:
                self.assertIn(f'href="{candidate["routes"]["en"]}"', rows)

    def test_current_detail_evidence_uses_eight_visible_then_static_archive(self):
        for issue in self.issues:
            document = self._document(issue, "en")
            section = document.split('id="published-evidence"', 1)[1].split(
                '<div class="issue-current-detail-grid issue-current-bottom-grid">',
                1,
            )[0]
            visible = section.split("<details", 1)[0]
            expected_visible = min(8, len(issue["evidence"]))
            expected_archive = max(0, len(issue["evidence"]) - 8)
            self.assertEqual(
                visible.count('class="issue-evidence-row"'),
                expected_visible,
            )
            self.assertEqual(
                section.count('class="issue-evidence-row"') - expected_visible,
                expected_archive,
            )
            self.assertEqual("<details" in section, expected_archive > 0)

    def test_current_detail_evidence_archive_requires_no_javascript(self):
        for issue in self.issues:
            document = self._document(issue, "fr")
            section = document.split('id="published-evidence"', 1)[1].split(
                '<div class="issue-current-detail-grid issue-current-bottom-grid">',
                1,
            )[0]
            if len(issue["evidence"]) > 8:
                self.assertIn('<details class="issue-evidence-archive">', section)
                self.assertIn("<summary>", section)
            self.assertNotIn("<button", section)
            self.assertNotIn("onclick=", section)
            self.assertNotIn("data-archive", section)

    def test_current_detail_compact_history_uses_coverage_history(self):
        for issue in self.issues:
            history = issue["coverage_history"]
            document = self._document(issue, "en")
            panel = document.split('aria-labelledby="compact-history-title"', 1)[1].split(
                "</section>", 1
            )[0]
            self.assertIn(builder._date(history["first_observation"], "en"), panel)
            self.assertIn(builder._date(history["last_observation"], "en"), panel)
            self.assertIn(f"<dd>{history['total_item_count']}</dd>", panel)
            self.assertIn(f"<dd>{history['active_day_count']}</dd>", panel)
            self.assertEqual(
                panel.count('class="issue-compact-history-bar"'),
                len(history["daily"]),
            )

    def test_current_detail_history_gateway_is_static(self):
        for issue in self.issues:
            for language in ("fr", "en"):
                document = self._document(issue, language)
                href = builder._history_route(issue, language)
                self.assertIn(
                    f'class="poll-detail-back-cta issue-history-detail-cta" href="{href}"',
                    document,
                )
                navigation = document.split(
                    '<div class="issue-detail-crosslinks">', 1
                )[1].split("</div>", 1)[0]
                self.assertNotIn("<button", navigation)

    def test_current_detail_related_issues_are_observed_evidence_intersections(self):
        for issue in self.issues:
            document = self._document(issue, "en")
            self.assertIn(
                "Shared published evidence; not ideological or policy similarity.",
                document,
            )
            self.assertNotIn("policy alignment", document)
            self.assertNotIn("candidate similarity", document)
            for related in issue["related_issues"]:
                self.assertIn(
                    f'data-related-issue="{related["issue_id"]}"',
                    document,
                )
                self.assertIn(
                    f'data-evidence-count="{len(related["evidence_ids"])}"',
                    document,
                )
                self.assertIn(
                    f'href="{related["routes"]["en"]}"',
                    document,
                )

    def test_current_detail_uses_five_zone_hero_kpi_contract(self):
        for issue in self.issues:
            for language in ("fr", "en"):
                document = self._document(issue, language)
                hero = document.split(
                    '<section class="poll-detail-hero issue-detail-hero"', 1
                )[1].split("</section>", 1)[0]
                self.assertIn('class="poll-detail-metrics issue-current-kpis"', hero)
                self.assertEqual(hero.count('class="poll-detail-metric"'), 4)
                self.assertEqual(hero.count('class="issue-weekly-signal"'), 1)
                self.assertIn(
                    builder._incidence_label(
                        issue["current_coverage"]["comparison_7d"]["latest_incidence"],
                        language,
                    ),
                    hero,
                )
                self.assertIn(
                    builder._signed_pp(
                        issue["current_coverage"]["comparison_7d"]["incidence_change_pp"],
                        language,
                    ),
                    hero,
                )

    def test_current_detail_activity_explains_measure_legend_and_incidence_denominator(self):
        french = self._document(self.issues[0], "fr")
        english = self._document(self.issues[0], "en")
        for phrase in (
            "ARTICLES PAR JOUR",
            "ANTÉRIEUR",
            "SEM. COMPLÈTE PRÉC.",
            "DERNIÈRE SEM. COMPLÈTE",
            "PARTIEL",
            "INCIDENCE · SEMAINES COMPLÈTES",
            "Jours-sources de cet enjeu ÷ jours-sources de couverture présidentielle retenue.",
        ):
            self.assertIn(phrase, french)
        for phrase in (
            "ITEMS PER DAY",
            "EARLIER",
            "PREVIOUS COMPLETE WEEK",
            "LATEST COMPLETE WEEK",
            "PARTIAL",
            "INCIDENCE · COMPLETE WEEKS",
            "Source-days for this issue ÷ accepted presidential-coverage source-days.",
        ):
            self.assertIn(phrase, english)

    def test_current_detail_candidate_a1_is_complete_two_column_ledger(self):
        for issue in self.issues:
            for language in ("fr", "en"):
                document = self._document(issue, language)
                section = document.split(
                    'aria-labelledby="candidate-associations-title"', 1
                )[1].split("</section>", 1)[0]
                candidates = issue["current_candidate_associations"]["candidates"]
                self.assertIn('class="issue-candidate-ledgers"', section)
                self.assertEqual(
                    section.count('class="issue-candidate-column '),
                    2,
                )
                self.assertEqual(
                    section.count('class="issue-candidate-magnitude"'),
                    len(candidates),
                )
                for candidate in candidates:
                    self.assertIn(
                        builder._h(candidate["candidate_name"]),
                        section,
                    )
                self.assertNotIn('class="issue-candidate-archive"', section)
                self.assertNotIn("MORE CANDIDATES", section)
                self.assertNotIn("CANDIDATS SUPPLÉMENTAIRES", section)
                self.assertNotIn("onclick=", section)

    def test_current_detail_optional_overflow_hooks_are_scoped(self):
        document = self._document(self.issues[0], "en")
        self.assertIn('class="issue-subtopics-scroll"', document)
        self.assertIn('class="issue-related-list issue-related-scroll"', document)
        stylesheet = (ROOT / "assets" / "issues.css").read_text(encoding="utf-8")
        for selector in (
            ".issue-current-detail-page .issue-subtopics-scroll",
            ".issue-current-detail-page .issue-candidate-column",
            ".issue-current-detail-page .issue-related-scroll",
        ):
            self.assertIn(selector, stylesheet)
        self.assertIn("overflow-y: auto", stylesheet)
        self.assertIn("scrollbar-gutter: stable", stylesheet)
        self.assertIn("overscroll-behavior: contain", stylesheet)

    def test_current_detail_tooltip_css_matches_candidate_typography_and_interaction(self):
        stylesheet = (ROOT / "assets" / "issues.css").read_text(encoding="utf-8")
        tooltip_rule = stylesheet.split(
            ".issue-current-detail-page .issue-note-tooltip-body {", 1
        )[1].split("}", 1)[0]
        self.assertIn("font-size: 12px", tooltip_rule)
        self.assertIn("font-weight: 500", tooltip_rule)
        self.assertIn("line-height: 1.42", tooltip_rule)
        self.assertIn("letter-spacing: normal", tooltip_rule)
        self.assertIn("text-transform: none", tooltip_rule)
        self.assertIn(
            ".issue-note-tooltip:hover\n  .issue-note-tooltip-body",
            stylesheet,
        )
        self.assertIn(
            ".issue-note-tooltip:focus-within\n  .issue-note-tooltip-body",
            stylesheet,
        )
        self.assertIn("outline: 2px solid var(--final-cyan)", stylesheet)
        self.assertIn("html:has(> body.issue-current-detail-page)", stylesheet)

    def test_current_detail_evidence_header_status_is_dynamic(self):
        for issue in self.issues:
            total = len(issue["evidence"])
            shown = min(8, total)
            english = self._document(issue, "en")
            expected = f'{total} {"ITEM" if total == 1 else "ITEMS"} · {shown} SHOWN'
            self.assertIn(expected, english)

    def test_current_detail_compact_history_uses_blue_visual_token_and_date_status(self):
        stylesheet = (ROOT / "assets" / "issues.css").read_text(encoding="utf-8")
        self.assertRegex(
            stylesheet,
            r"\.issue-compact-history-bar\s*\{[^}]*var\(--final-blue\)",
        )
        for issue in self.issues:
            history = issue["coverage_history"]
            english = self._document(issue, "en")
            status = (
                f'{builder._date(history["first_observation"], "en")} → '
                f'{builder._date(history["last_observation"], "en")}'
            )
            self.assertIn(status, english)

    def test_current_detail_bottom_navigation_has_primary_history_and_secondary_all(self):
        document = self._document(self.issues[0], "en")
        navigation = document.split(
            '<div class="issue-detail-crosslinks">', 1
        )[1].split("</div>", 1)[0]
        self.assertIn("issue-history-detail-cta", navigation)
        self.assertIn("issue-all-cta", navigation)
        stylesheet = (ROOT / "assets" / "issues.css").read_text(encoding="utf-8")
        self.assertIn(".issue-current-detail-page .issue-history-detail-cta", stylesheet)
        self.assertIn(".issue-current-detail-page .issue-all-cta", stylesheet)

    def test_current_detail_redesign_does_not_enter_history_detail_renderer(self):
        source = inspect.getsource(builder.render_history_detail)
        for marker in (
            "issue-current-detail-page",
            "_current_activity_microbars",
            "_current_evidence",
            "issue-compact-history",
            "issue-cooccurring",
        ):
            self.assertNotIn(marker, source)

    def test_current_detail_source_render_is_deterministic(self):
        first = builder.build_from_paths(write=False)["artifacts"]
        second = builder.build_from_paths(write=False)["artifacts"]
        for issue in self.issues:
            for language in ("fr", "en"):
                path = self._path(issue, language)
                self.assertEqual(first[path], second[path])

    def test_current_detail_pass_does_not_add_live_fetch_to_details(self):
        # Live fetching is gated by a current-hub grid contract; detail pages stay static.
        for issue in self.issues:
            for language in ("fr", "en"):
                markup = self.artifacts[self._path(issue, language)].decode("utf-8")
                self.assertNotIn("data-issue-live-url", markup)


    def test_issue_family_tiny_mobile_masthead_contract(self):
        stylesheet = (ROOT / "assets" / "issues.css").read_text(encoding="utf-8")
        tiny = stylesheet.split(
            "FR27 Issues tiny-mobile masthead lock", 1
        )[1].split(
            "FR27 Issues comparison fixed-height scroll contract", 1
        )[0]
        self.assertIn("@media (max-width: 479px)", tiny)
        self.assertIn(".issues-page .candidate-masthead", tiny)
        self.assertRegex(
            tiny,
            r"\.issues-page \.candidate-countdown \{[^}]*order: 1;",
        )
        self.assertRegex(
            tiny,
            r"\.issues-page \.candidate-language \{[^}]*order: 2;",
        )


class HistoricalIssueDetailRedesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = builder.build_from_paths(write=False)
        cls.projection = cls.result["projection"]
        cls.artifacts = cls.result["artifacts"]
        cls.issues = cls.projection["issues"]
        cls.stylesheet = (ROOT / "assets" / "issues.css").read_text(
            encoding="utf-8"
        )

    @staticmethod
    def _path(issue, language, *, history=True):
        route = (
            builder._history_route(issue, language)
            if history
            else issue["routes"][language]
        )
        return Path(route.strip("/")) / "index.html"

    def _document(self, issue, language):
        return self.artifacts[self._path(issue, language)].decode("utf-8")

    @staticmethod
    def _source_digest(artifacts, paths):
        digest = hashlib.sha256()
        for path in sorted(paths):
            digest.update(path.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(artifacts[path])
        return digest.hexdigest()

    def test_history_detail_uses_locked_composition_without_hero_cta(self):
        for issue in self.issues:
            for language in ("fr", "en"):
                document = self._document(issue, language)
                hero = document.split(
                    '<section class="poll-detail-hero issue-detail-hero"', 1
                )[1].split("</section>", 1)[0]
                self.assertEqual(
                    len(
                        re.findall(
                            r'class="poll-detail-metric(?: poll-detail-metric-fieldwork)?"',
                            hero,
                        )
                    ),
                    5,
                )
                self.assertNotIn("poll-detail-source-cta", hero)
                markers = (
                    "issue-history-detail-top-grid",
                    "issue-history-candidates",
                    "issue-history-daily",
                    "issue-history-detail-actions",
                )
                positions = [document.index(marker) for marker in markers]
                self.assertEqual(positions, sorted(positions))

    def test_history_detail_uses_compact_bars_and_peak_days(self):
        for issue in self.issues:
            history = issue["coverage_history"]
            active_days = [
                point
                for point in history["daily"]
                if point["item_count"] > 0
            ]
            expected_peaks = min(5, len(active_days))

            for language in ("fr", "en"):
                document = self._document(issue, language)

                self.assertIn('data-history-mode="volume"', document)
                self.assertIn('data-history-mode="share"', document)

                self.assertIn(
                    'class="issue-history-detail-bars"',
                    document,
                )

                self.assertEqual(
                    document.count('class="issue-history-detail-bar"'),
                    len(history["daily"]),
                )

                self.assertIn(
                    'class="issue-history-peak-days"',
                    document,
                )

                self.assertEqual(
                    document.count('data-peak-day="'),
                    expected_peaks,
                )

                self.assertNotIn(
                    'class="issue-history-chart"',
                    document,
                )

                self.assertNotIn(
                    'class="issue-history-context-list"',
                    document,
                )

                self.assertIn(
                    builder._date(history["peak"]["date"], language),
                    document,
                )

    def test_history_method_note_uses_accessible_tooltip_pattern(self):
        for issue in self.issues:
            for language in ("fr", "en"):
                document = self._document(issue, language)
                self.assertRegex(
                    document,
                    r'<button class="issue-note-tooltip-trigger" type="button" '
                    r'aria-label="[^"]+" '
                    r'aria-describedby="issue-history-denominator-note">i</button>',
                )
                self.assertIn(
                    'id="issue-history-denominator-note" role="tooltip"',
                    document,
                )
        self.assertRegex(
            self.stylesheet,
            r"\.issue-history-detail-page \.issue-note-tooltip-body \{[^}]*"
            r"font-size: 12px;[^}]*font-weight: 500;[^}]*line-height: 1\.42;",
        )
        self.assertIn(
            ".issue-history-detail-page\n  .issue-note-tooltip:hover .issue-note-tooltip-body",
            self.stylesheet,
        )
        self.assertIn(
            ".issue-note-tooltip:focus-within .issue-note-tooltip-body",
            self.stylesheet,
        )

    def test_history_typography_reuses_candidate_dossier_contract(self):
        stylesheet = self.stylesheet

        old_marker = (
            "FR27 HISTORICAL DOSSIER — CANDIDATE TYPOGRAPHY PARITY"
        )
        shared_marker = (
            "FR27 ISSUES — SHARED CANDIDATE TYPOGRAPHY CONTRACT"
        )

        # The discarded Codex historical-only typography layer must stay gone.
        self.assertNotIn(old_marker, stylesheet)

        # All Issues URL families now share one Candidate-style contract.
        self.assertIn(shared_marker, stylesheet)

        typography = stylesheet.split(
            shared_marker,
            1,
        )[1]

        # Shared font family across hub/current/history families.
        self.assertIn(".issues-page,", typography)
        self.assertIn(".issues-hub-page,", typography)
        self.assertIn(".issue-current-detail-page,", typography)
        self.assertIn(".issue-history-detail-page {", typography)
        self.assertIn(
            "font-family: var(--fr27-type-sans);",
            typography,
        )

        # Candidate dossier root rhythm.
        self.assertIn(".issues-page {", typography)
        self.assertIn("font-size: 14px;", typography)
        self.assertIn("font-weight: 400;", typography)
        self.assertIn("line-height: 1.5;", typography)

        # Candidate-style responsive dossier title.
        self.assertIn(
            ".issues-page .poll-detail-title {",
            typography,
        )
        self.assertIn(
            "font-size: clamp(27px, 2.25vw, 34px);",
            typography,
        )
        self.assertIn(
            "font-weight: 720;",
            typography,
        )
        self.assertIn(
            "line-height: 1.08;",
            typography,
        )

        # Shared panel-heading role.
        self.assertIn(
            ".issues-page .poll-detail-panel-head h2 {",
            typography,
        )
        self.assertIn(
            "font-size: var(--fr27-type-panel-heading);",
            typography,
        )

        # Body/meta/control/action roles come from FR27 shared tokens.
        self.assertIn(
            "font-size: var(--fr27-type-body);",
            typography,
        )
        self.assertIn(
            "font-size: var(--fr27-type-meta);",
            typography,
        )
        self.assertIn(
            "font-size: var(--fr27-type-control);",
            typography,
        )
        self.assertIn(
            "font-size: var(--fr27-type-action);",
            typography,
        )

        # Tooltip prose follows the Candidate reading contract.
        self.assertIn(
            ".issues-page .issue-note-tooltip-body,",
            typography,
        )
        self.assertIn(
            "font-family: var(--fr27-type-sans);",
            typography,
        )
        self.assertIn("font-size: 12px;", typography)
        self.assertIn("font-weight: 500;", typography)
        self.assertIn("line-height: 1.42;", typography)
        self.assertIn("letter-spacing: normal;", typography)
        self.assertIn("text-transform: none;", typography)

        # Do not restore the historical-only 13px type-token island.
        self.assertNotIn(
            ".issue-history-detail-page {\n"
            "  --fr27-type-body: 13px;",
            stylesheet,
        )

    def test_history_candidate_ledgers_render_every_record_and_route(self):
        for issue in self.issues:
            candidates = issue["historical_candidate_associations"]["candidates"]
            for language in ("fr", "en"):
                document = self._document(issue, language)
                candidate_section = document.split(
                    'class="poll-detail-panel issue-history issue-history-candidates"',
                    1,
                )[1].split("</section>", 1)[0]
                self.assertEqual(
                    candidate_section.count('data-association-count="'),
                    len(candidates),
                )
                self.assertEqual(
                    candidate_section.count(
                        'class="issue-history-candidate-column '
                    ),
                    2,
                )
                self.assertNotIn("<details", candidate_section)
                self.assertNotIn("SHOW MORE", candidate_section)
                self.assertNotIn("AFFICHER", candidate_section)
                for candidate in candidates:
                    self.assertIn(
                        f'data-association-count="{candidate["association_count"]}"',
                        candidate_section,
                    )
                    route = candidate["routes"].get(language)
                    if route:
                        self.assertIn(f'href="{route}"', candidate_section)

    def test_history_candidate_tooltip_preserves_semantic_boundary(self):
        french = self._document(self.issues[0], "fr")
        english = self._document(self.issues[0], "en")
        self.assertIn(
            "Elle ne décrit ni soutien, ni opposition, ni priorité, ni idéologie, "
            "ni position politique, ni engagement de programme.",
            french,
        )
        self.assertIn(
            "It does not imply support, opposition, priority, ideology, a political "
            "position, or a programme or manifesto commitment.",
            english,
        )
        for document in (french, english):
            self.assertIn(
                'aria-describedby="issue-history-candidate-note"', document
            )
            self.assertIn(
                'id="issue-history-candidate-note" role="tooltip"', document
            )

    def test_history_daily_ledger_preserves_every_observation_and_column(self):
        for issue in self.issues:
            daily = issue["coverage_history"]["daily"]
            for language in ("fr", "en"):
                document = self._document(issue, language)
                ledger = document.split(
                    'class="issue-history-table-wrap issue-history-daily-ledger"',
                    1,
                )[1].split("</table>", 1)[0]
                self.assertEqual(ledger.count("<tr>"), len(daily) + 1)
                self.assertEqual(ledger.count('data-label="'), len(daily) * 5)
                for point in daily:
                    self.assertIn(f'datetime="{point["date"]}"', ledger)

    def test_history_scroll_and_responsive_hooks_are_scoped(self):
        history_css = self.stylesheet.split(
            "FR27 HISTORICAL ISSUE DOSSIER — CURRENT-DETAIL PARITY", 1
        )[1]
        self.assertIn(
            "grid-template-columns: minmax(0, 17fr) minmax(300px, 8fr);",
            history_css,
        )
        self.assertRegex(
            history_css,
            r"\.issue-history-detail-page \.issue-history-candidate-column "
            r"\{[^}]*max-height: 206px;[^}]*overflow-y: auto;[^}]*"
            r"scrollbar-gutter: stable;",
        )
        self.assertRegex(
            history_css,
            r"\.issue-history-detail-page \.issue-history-daily-ledger \{[^}]*"
            r"max-height: 230px;[^}]*overflow-x: hidden;[^}]*overflow-y: auto;",
        )
        self.assertRegex(
            history_css,
            r"\.issue-history-detail-page \.issue-history-table thead \{[^}]*"
            r"position: sticky;",
        )
        responsive = history_css.split("@media screen and (max-width: 999px)", 1)[1]
        self.assertIn("overflow-y: visible;", responsive)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", responsive)

    def test_locked_source_renders_remain_byte_identical(self):
        manifest = self.result["manifest"]
        hubs = (
            Path("enjeux/index.html"),
            Path("en/issues/index.html"),
            Path("enjeux/historique/index.html"),
            Path("en/issues/history/index.html"),
        )
        current_details = [
            Path(page[key].strip("/")) / "index.html"
            for page in manifest["pages"]
            for key in ("page_path_fr", "page_path_en")
        ]
        for path in (*hubs, *current_details):
            self.assertEqual(
                self.artifacts[path],
                (ROOT / path).read_text(encoding="utf-8").encode("utf-8"),
            )

    def test_history_detail_is_bilingual_and_source_deterministic(self):
        second = builder.build_from_paths(write=False)["artifacts"]
        for issue in self.issues:
            french = self._document(issue, "fr")
            english = self._document(issue, "en")
            self.assertIn("JOURS MARQUANTS", french)
            self.assertIn("PEAK DAYS", english)
            self.assertIn("REGISTRE JOUR PAR JOUR", french)
            self.assertIn("DAY-BY-DAY LEDGER", english)
            for language in ("fr", "en"):
                path = self._path(issue, language)
                self.assertEqual(self.artifacts[path], second[path])


if __name__ == "__main__":
    unittest.main()
