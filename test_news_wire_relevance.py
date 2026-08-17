import copy
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

from http_fetch import HttpFetchResult
from fetch_news_wire import (
    CANDIDATE_VISIBILITY_METHOD,
    CANDIDATE_VISIBILITY_THRESHOLDS,
    DISCOVERY_QUERIES,
    DIRECT_ENTRY_LIMIT,
    DISCOVERY_ENTRY_LIMIT,
    FETCH_WORKERS,
    GOOGLE_NEWS_WORKERS,
    INVENTORY_SCHEMA_VERSION,
    NEWS_CANDIDATE_ALIAS_OVERRIDES,
    PUBLISHER_POLICY,
    PUBLISHER_SITE_ENTRY_LIMIT,
    SOURCES,
    accept_discovery_entries,
    aggregate_discovered_publishers,
    build_candidate_visibility,
    build_source_health_routes,
    build_wire,
    build_google_news_url,
    candidate_names_from_matches,
    classify_candidate_coverage_scope,
    classify_notable_development,
    classify_relevant_news,
    classify_structured_electoral_support,
    count_contributing_media_publishers,
    current_presidential_matches,
    deduplicate_entries,
    entry_transport,
    explicit_election_match,
    generate_discovery_queries,
    generate_publisher_site_feeds,
    is_static_entity_page,
    limit_items,
    load_inventory,
    match_news_candidates,
    merge_inventory,
    normalize,
    normalize_domain,
    parse_feed,
    publisher_policy_match,
    publisher_site_feed_due,
    remove_publisher_suffix,
    stable_slot,
    transport_priority,
    validate_candidate_visibility,
    validate_output,
)


def successful_fetch(body, url):
    return HttpFetchResult(
        success=True,
        not_modified=False,
        status_code=200,
        response_body=body,
        final_url=url,
        attempts=1,
        elapsed_ms=0,
        etag=None,
        last_modified=None,
        failure_category=None,
        failure_message=None,
        response_bytes=len(body),
        retry_after_used=False,
    )


def not_modified_fetch(url):
    return HttpFetchResult(
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


def lcp_retrospective_summary() -> str:
    intro = (
        "Les élus insoumis annoncent un hommage historique. "
        "Le mouvement de Jean-Luc Mélenchon revendique cet héritage. "
        + ("La chronique retrace la Révolution française. " * 55)
    )
    retrospective = (
        "En 2024, lors d'un meeting pour les élections européennes, "
        "le leader de La France insoumise avait cité le fondateur de "
        "Place publique, Raphaël Glucksmann."
    )
    summary = intro + retrospective
    summary += " " + ("x" * (3232 - len(summary) - 1))
    if len(summary) != 3232:
        raise AssertionError("LCP regression summary must stay at 3,232 characters")
    return summary


class NewsWireRelevanceTests(unittest.TestCase):
    def test_feed_entry_and_concurrency_limits(self):
        self.assertEqual(DIRECT_ENTRY_LIMIT, 20)
        self.assertEqual(DISCOVERY_ENTRY_LIMIT, 20)
        self.assertEqual(PUBLISHER_SITE_ENTRY_LIMIT, 5)
        self.assertLessEqual(FETCH_WORKERS, 12)
        self.assertEqual(GOOGLE_NEWS_WORKERS, 4)

    def test_registry_declares_source_specificity(self):
        configured_sources = json.loads(
            Path("news_sources.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(SOURCES), len(configured_sources))
        self.assertTrue(all(
            isinstance(source.get("politics_specific"), bool)
            for source in SOURCES
        ))

    def test_marianne_uses_publisher_site_route_only(self):
        self.assertNotIn(
            "marianne-general",
            {source["source_id"] for source in SOURCES},
        )

        publisher_site_feeds = generate_publisher_site_feeds()
        marianne_feed = next(
            feed
            for feed in publisher_site_feeds
            if feed["id"] == "publisher-site:marianne.net"
        )
        self.assertEqual(marianne_feed["publisher"], "Marianne")
        self.assertEqual(marianne_feed["tier"], "core")
        self.assertEqual(marianne_feed["interval_hours"], 3)

        routes = build_source_health_routes(
            generate_discovery_queries(
                ["Alpha", "Bravo", "Charlie", "Delta"]
            ),
            publisher_site_feeds,
            datetime(2026, 7, 28, 2, tzinfo=timezone.utc),
        )
        routes_by_id = {route["route_id"]: route for route in routes}
        self.assertNotIn("direct:marianne-general", routes_by_id)
        self.assertEqual(
            routes_by_id["publisher-site:marianne.net"]["schedule_class"],
            "every_3_hours",
        )

    def test_full_candidate_name_matches_headline_with_provenance(self):
        matches = match_news_candidates(
            "Édouard Philippe prépare sa candidature",
            "",
            ["Édouard Philippe"],
        )

        self.assertEqual(
            matches,
            [
                {
                    "candidate": "Édouard Philippe",
                    "matched_aliases": ["edouard philippe"],
                    "locations": ["headline"],
                }
            ],
        )
        self.assertEqual(
            candidate_names_from_matches(matches),
            ["Édouard Philippe"],
        )

    def test_candidate_match_is_accent_and_punctuation_insensitive(self):
        for headline in (
            "Edouard Philippe prépare sa candidature",
            "Édouard—Philippe prépare sa candidature",
        ):
            with self.subTest(headline=headline):
                self.assertEqual(
                    match_news_candidates(
                        headline,
                        "",
                        ["Édouard Philippe"],
                    ),
                    [
                        {
                            "candidate": "Édouard Philippe",
                            "matched_aliases": ["edouard philippe"],
                            "locations": ["headline"],
                        }
                    ],
                )

    def test_candidate_match_rejects_other_people_named_philippe(self):
        for headline in (
            "Philippe Étienne revient sur sa carrière diplomatique",
            "Le ministre Philippe Tabarot présente la réforme",
            "Un entretien avec Philippe Étienne",
            "Philippe présente la réforme",
        ):
            with self.subTest(headline=headline):
                matches = match_news_candidates(
                    headline,
                    "",
                    ["Édouard Philippe"],
                )
                self.assertEqual(matches, [])
                self.assertEqual(candidate_names_from_matches(matches), [])

    def test_candidate_match_preserves_summary_only_location(self):
        headline = "Le débat politique continue"
        summary = "Jean-Luc Mélenchon prépare sa candidature"
        matches = match_news_candidates(
            headline,
            summary,
            ["Jean-Luc Mélenchon"],
        )

        self.assertEqual(
            matches,
            [
                {
                    "candidate": "Jean-Luc Mélenchon",
                    "matched_aliases": ["jean luc melenchon"],
                    "locations": ["summary"],
                }
            ],
        )
        self.assertIsNone(
            classify_relevant_news(
                normalize(headline),
                normalize(summary),
                candidate_names_from_matches(matches),
                matches,
            )
        )

    def test_candidate_match_combines_headline_and_summary_locations(self):
        matches = match_news_candidates(
            "Jean-Luc Mélenchon prépare sa candidature",
            "Jean-Luc Mélenchon détaille ensuite son calendrier",
            ["Jean-Luc Mélenchon"],
        )
        self.assertEqual(matches[0]["matched_aliases"], ["jean luc melenchon"])
        self.assertEqual(matches[0]["locations"], ["headline", "summary"])

    def test_candidate_match_requires_token_boundaries(self):
        self.assertEqual(
            match_news_candidates(
                "Le collectif Neoedouard Philippeville se réunit",
                "",
                ["Édouard Philippe"],
            ),
            [],
        )

    def test_candidate_matches_are_sorted_and_deduplicated(self):
        matches = match_news_candidates(
            "Marine Le Pen débat avec Jean-Luc Mélenchon et Marine Le Pen",
            "",
            ["Marine Le Pen", "Jean-Luc Mélenchon", "Marine Le Pen"],
        )
        self.assertEqual(
            candidate_names_from_matches(matches),
            ["Jean-Luc Mélenchon", "Marine Le Pen"],
        )
        self.assertTrue(all(match["locations"] == ["headline"] for match in matches))

    def test_no_unreviewed_candidate_aliases_are_approved(self):
        self.assertEqual(NEWS_CANDIDATE_ALIAS_OVERRIDES, {})
        self.assertNotIn("Philippe", NEWS_CANDIDATE_ALIAS_OVERRIDES)
        self.assertEqual(
            match_news_candidates(
                "Philippe prépare sa candidature",
                "",
                ["Philippe"],
            ),
            [],
        )

    def test_discovery_static_configuration_contract(self):
        expected_fields = {"id", "label", "query", "enabled"}
        static_ids = []

        for record in DISCOVERY_QUERIES:
            self.assertEqual(set(record), expected_fields)
            self.assertIsInstance(record["id"], str)
            self.assertTrue(record["id"].strip())
            self.assertIsInstance(record["label"], str)
            self.assertTrue(record["label"].strip())
            self.assertIsInstance(record["query"], str)
            self.assertIs(type(record["enabled"]), bool)
            if record["enabled"]:
                self.assertIn("when:3d", record["query"])
            static_ids.append(record["id"])

        self.assertEqual(len(static_ids), len(set(static_ids)))

        generated = generate_discovery_queries(
            ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
        )
        generated_ids = {
            query["id"]
            for query in generated
            if query["kind"] == "candidate"
        }
        self.assertTrue(generated_ids.isdisjoint(static_ids))

    def test_publisher_policy_configuration_contract(self):
        expected_fields = {"name", "source_type", "tier", "enabled"}
        source_types = set()

        self.assertGreaterEqual(len(PUBLISHER_POLICY), 100)
        for domain, record in PUBLISHER_POLICY.items():
            self.assertEqual(domain, domain.lower())
            self.assertEqual(domain, normalize_domain(domain))
            self.assertEqual(set(record), expected_fields)
            self.assertIsInstance(record["name"], str)
            self.assertTrue(record["name"].strip())
            self.assertIn(
                record["source_type"],
                {"media", "official", "fact_check"},
            )
            self.assertIn(record["tier"], {"core", "extended"})
            self.assertIs(type(record["enabled"]), bool)
            source_types.add(record["source_type"])

        self.assertEqual(
            source_types,
            {"media", "official", "fact_check"},
        )
        self.assertGreaterEqual(
            sum(
                record["enabled"]
                and record["source_type"] == "media"
                for record in PUBLISHER_POLICY.values()
            ),
            180,
        )

        for source in SOURCES:
            match = publisher_policy_match(
                normalize_domain(source["feed_url"])
            )
            if match is None:
                continue
            _domain, policy = match
            if policy["source_type"] == "media":
                self.assertEqual(policy["name"], source["name"])

    def test_publisher_site_feed_registry_matches_enabled_media_policy(self):
        feeds = generate_publisher_site_feeds()
        expected_domains = {
            domain
            for domain, record in PUBLISHER_POLICY.items()
            if record["enabled"] and record["source_type"] == "media"
        }

        self.assertEqual(
            {feed["domain"] for feed in feeds},
            expected_domains,
        )
        self.assertTrue(all(
            PUBLISHER_POLICY[feed["domain"]]["source_type"] == "media"
            for feed in feeds
        ))
        self.assertFalse(any(
            record["source_type"] in {"official", "fact_check"}
            and domain in {feed["domain"] for feed in feeds}
            for domain, record in PUBLISHER_POLICY.items()
        ))

    def test_publisher_site_feed_ids_and_queries_are_stable(self):
        first = generate_publisher_site_feeds()
        second = generate_publisher_site_feeds()
        ids = [feed["id"] for feed in first]
        configured_ids = (
            [source["source_id"] for source in SOURCES]
            + [
                f"discovery:{query['id']}"
                for query in generate_discovery_queries(
                    ["Alpha", "Bravo", "Charlie", "Delta"]
                )
            ]
            + ids
        )

        self.assertEqual(first, second)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(configured_ids), len(set(configured_ids)))
        self.assertGreaterEqual(len(first), 180)
        self.assertGreater(
            len(SOURCES) + len(DISCOVERY_QUERIES) + 5 + len(first),
            200,
        )

        for feed in first:
            self.assertEqual(
                feed["id"],
                f"publisher-site:{feed['domain']}",
            )
            self.assertIn(f"site:{feed['domain']}", feed["query"])
            self.assertIn("when:7d", feed["query"])
            self.assertNotIn("Candidate", feed["query"])
            self.assertIn("hl=fr", feed["feed_url"])
            self.assertIn("gl=FR", feed["feed_url"])
            self.assertIn("ceid=FR%3Afr", feed["feed_url"])

    def test_publisher_site_schedule_covers_every_feed_in_twelve_hours(self):
        feeds = generate_publisher_site_feeds()
        start = datetime(2026, 7, 23, 0, tzinfo=timezone.utc)
        hours = [start + timedelta(hours=hour) for hour in range(12)]

        for feed in feeds:
            due_hours = [
                hour.hour
                for hour in hours
                if publisher_site_feed_due(feed, hour)
            ]
            expected_count = 4 if feed["tier"] == "core" else 1
            self.assertEqual(len(due_hours), expected_count)

            minimum_gap = 3 if feed["tier"] == "core" else 12
            if len(due_hours) > 1:
                self.assertTrue(all(
                    later - earlier >= minimum_gap
                    for earlier, later in zip(due_hours, due_hours[1:])
                ))

        covered = {
            feed["id"]
            for hour in hours
            for feed in feeds
            if publisher_site_feed_due(feed, hour)
        }
        self.assertEqual(covered, {feed["id"] for feed in feeds})

    def test_core_and_extended_slots_have_exact_cycle_frequency(self):
        feeds = generate_publisher_site_feeds()
        start = datetime(2026, 7, 23, 0, tzinfo=timezone.utc)

        for feed in feeds:
            interval = feed["interval_hours"]
            self.assertEqual(
                feed["slot"],
                stable_slot(feed["id"], interval),
            )
            for cycle_start in range(0, 12, interval):
                cycle = [
                    start + timedelta(hours=hour)
                    for hour in range(cycle_start, cycle_start + interval)
                ]
                self.assertEqual(
                    sum(publisher_site_feed_due(feed, hour) for hour in cycle),
                    1,
                )

    def test_discovery_source_files_are_utf8_without_mojibake(self):
        for filename in (
            "fetch_news_wire.py",
            "test_news_wire_relevance.py",
            "discovery_queries.json",
            "publisher_policy.json",
        ):
            text = Path(filename).read_bytes().decode("utf-8")
            markers = (
                chr(0x251C),
                chr(0x0393) + chr(0x00C7),
                chr(0xFFFD),
            )
            for marker in markers:
                self.assertNotIn(marker, text)
            if filename.endswith(".json"):
                json.loads(text)

    def test_discovery_queries_are_generated_from_stable_candidate_groups(self):
        candidates = [f"Candidate {index:02d}" for index in range(1, 21)]
        first = generate_discovery_queries(candidates)
        second = generate_discovery_queries(candidates)

        self.assertEqual(first, second)
        self.assertEqual(len(first), len(DISCOVERY_QUERIES) + 5)
        self.assertEqual(
            [query["id"] for query in first[-5:]],
            [f"candidate-group-{index:02d}" for index in range(1, 6)],
        )
        self.assertTrue(all("when:3d" in query["query"] for query in first))
        self.assertTrue(all(query["feed_url"].startswith(
            "https://news.google.com/rss/search?"
        ) for query in first))

    def test_discovery_query_ids_are_unique(self):
        queries = generate_discovery_queries(
            ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
        )
        ids = [query["id"] for query in queries]
        self.assertEqual(len(ids), len(set(ids)))

    def test_google_news_url_uses_french_parameters(self):
        url = build_google_news_url('"présidentielle 2027" when:3d')
        self.assertIn("hl=fr", url)
        self.assertIn("gl=FR", url)
        self.assertIn("ceid=FR%3Afr", url)
        self.assertIn("q=", url)

    def test_publisher_domain_normalization_and_subdomain_matching(self):
        self.assertEqual(
            normalize_domain("HTTPS://WWW.POLITIQUE.LEFIGARO.FR/path"),
            "politique.lefigaro.fr",
        )
        match = publisher_policy_match("politique.lefigaro.fr")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "lefigaro.fr")
        self.assertEqual(match[1]["name"], "Le Figaro")

    def test_google_news_parser_extracts_actual_publisher(self):
        raw = """<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel><item>
          <title>Présidentielle 2027 : un nouvel accord - Le Monde</title>
          <link>https://news.google.com/rss/articles/example</link>
          <pubDate>Wed, 22 Jul 2026 08:00:00 GMT</pubDate>
          <description>Un article politique.</description>
          <source url='https://www.lemonde.fr'>Le Monde</source>
        </item></channel></rss>""".encode("utf-8")
        entries = parse_feed(
            raw,
            "Discovery",
            "https://news.google.com/rss/search?q=test",
            google_news=True,
        )
        self.assertEqual(entries[0]["reported_publisher"], "Le Monde")
        self.assertEqual(entries[0]["publisher_domain"], "lemonde.fr")
        self.assertEqual(
            entries[0]["headline"],
            "Présidentielle 2027 : un nouvel accord",
        )

    def test_publisher_site_feed_may_return_no_matching_items(self):
        raw = (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<rss version='2.0'><channel></channel></rss>"
        ).encode("utf-8")
        entries = parse_feed(
            raw,
            "Publisher site",
            "https://news.google.com/rss/search?q=site%3Aexample.fr",
            google_news=True,
            max_entries=5,
            allow_empty=True,
        )
        self.assertEqual(entries, [])

    def test_approved_media_discovery_is_accepted(self):
        entry = {
            "reported_publisher": "Le Figaro",
            "publisher_domain": "politique.lefigaro.fr",
            "publisher": "Le Figaro",
            "headline": "Présidentielle 2027 : une candidature",
            "summary": "",
            "url": "https://news.google.com/rss/articles/approved",
            "canonical_url": "https://news.google.com/rss/articles/approved",
            "feed_url": "https://news.google.com/rss/search?q=test",
            "published_at": datetime(2026, 7, 22, tzinfo=timezone.utc),
        }
        accepted, rejected = accept_discovery_entries([entry], "test-query")
        self.assertEqual(rejected, [])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["publisher"], "Le Figaro")
        self.assertEqual(accepted[0]["source_id"], "discovery:test-query")

    def test_publisher_site_acceptance_enforces_configured_domain(self):
        base_entry = {
            "reported_publisher": "Le Figaro",
            "publisher": "Le Figaro",
            "headline": "Présidentielle 2027 : une candidature",
            "summary": "",
            "url": "https://news.google.com/rss/articles/site-domain",
            "canonical_url": (
                "https://news.google.com/rss/articles/site-domain"
            ),
            "feed_url": "https://news.google.com/rss/search?q=test",
            "published_at": datetime(2026, 7, 22, tzinfo=timezone.utc),
        }

        for domain in ("lefigaro.fr", "politique.lefigaro.fr"):
            with self.subTest(domain=domain):
                entry = dict(base_entry, publisher_domain=domain)
                accepted, rejected = accept_discovery_entries(
                    [entry],
                    "publisher-site:lefigaro.fr",
                    source_id_prefix="publisher-site",
                    expected_policy_domain="lefigaro.fr",
                    transport="publisher_site",
                )
                self.assertEqual(rejected, [])
                self.assertEqual(len(accepted), 1)
                self.assertEqual(accepted[0]["publisher"], "Le Figaro")
                self.assertEqual(
                    accepted[0]["publisher_domain"],
                    "lefigaro.fr",
                )

    def test_publisher_site_rejects_different_approved_domain(self):
        entry = {
            "reported_publisher": "Le Monde",
            "publisher_domain": "www.lemonde.fr",
            "publisher": "Le Monde",
            "headline": "Présidentielle 2027 : une candidature",
            "summary": "",
            "url": "https://news.google.com/rss/articles/site-mismatch",
            "canonical_url": (
                "https://news.google.com/rss/articles/site-mismatch"
            ),
            "feed_url": "https://news.google.com/rss/search?q=test",
            "published_at": datetime(2026, 7, 22, tzinfo=timezone.utc),
        }
        accepted, rejected = accept_discovery_entries(
            [entry],
            "publisher-site:lefigaro.fr",
            source_id_prefix="publisher-site",
            expected_policy_domain="lefigaro.fr",
            transport="publisher_site",
        )
        self.assertEqual(accepted, [])
        self.assertEqual(
            rejected[0]["rejection_reason"],
            "publisher_site_domain_mismatch",
        )
        self.assertEqual(rejected[0]["transport"], "publisher_site")

    def test_publisher_site_unresolved_and_unapproved_remain_rejected(self):
        base_entry = {
            "reported_publisher": "Unknown Outlet",
            "publisher": "Unknown Outlet",
            "headline": "Présidentielle 2027 : une actualité",
            "summary": "",
            "url": "https://news.google.com/rss/articles/site-unknown",
            "canonical_url": (
                "https://news.google.com/rss/articles/site-unknown"
            ),
            "feed_url": "https://news.google.com/rss/search?q=test",
            "published_at": datetime(2026, 7, 22, tzinfo=timezone.utc),
        }
        entries = [
            dict(base_entry, publisher_domain=""),
            dict(base_entry, publisher_domain="news.unknown.example"),
        ]
        accepted, rejected = accept_discovery_entries(
            entries,
            "publisher-site:lefigaro.fr",
            source_id_prefix="publisher-site",
            expected_policy_domain="lefigaro.fr",
            transport="publisher_site",
        )
        self.assertEqual(accepted, [])
        self.assertEqual(
            [item["rejection_reason"] for item in rejected],
            ["unresolved_publisher_domain", "publisher_not_approved"],
        )
        self.assertTrue(all(
            item["transport"] == "publisher_site"
            for item in rejected
        ))

    def test_shared_discovery_accepts_any_approved_media_domain(self):
        entries = []
        for publisher, domain in (
            ("Le Figaro", "politique.lefigaro.fr"),
            ("Le Monde", "www.lemonde.fr"),
        ):
            entries.append(
                {
                    "reported_publisher": publisher,
                    "publisher_domain": domain,
                    "publisher": publisher,
                    "headline": "Présidentielle 2027 : une candidature",
                    "summary": "",
                    "url": f"https://news.google.com/rss/articles/{domain}",
                    "canonical_url": (
                        f"https://news.google.com/rss/articles/{domain}"
                    ),
                    "feed_url": "https://news.google.com/rss/search?q=test",
                    "published_at": datetime(
                        2026, 7, 22, tzinfo=timezone.utc
                    ),
                }
            )

        accepted, rejected = accept_discovery_entries(
            entries,
            "shared-query",
        )
        self.assertEqual(rejected, [])
        self.assertEqual(
            {entry["publisher"] for entry in accepted},
            {"Le Figaro", "Le Monde"},
        )

    def test_unknown_discovery_publisher_is_quarantined(self):
        entry = {
            "reported_publisher": "Unknown Outlet",
            "publisher_domain": "news.unknown.example",
            "publisher": "Unknown Outlet",
            "headline": "Présidentielle 2027 : une actualité",
            "summary": "",
            "url": "https://news.google.com/rss/articles/unknown",
            "canonical_url": "https://news.google.com/rss/articles/unknown",
            "feed_url": "https://news.google.com/rss/search?q=test",
            "published_at": datetime(2026, 7, 22, tzinfo=timezone.utc),
        }
        accepted, rejected = accept_discovery_entries([entry], "test-query")
        self.assertEqual(accepted, [])
        self.assertEqual(rejected[0]["rejection_reason"], "publisher_not_approved")
        review = aggregate_discovered_publishers(rejected)
        self.assertEqual(review["publisher_count"], 1)
        self.assertEqual(review["item_count"], 1)
        self.assertEqual(
            review["publishers"][0]["transports"],
            ["shared_discovery"],
        )

    def test_non_media_discovery_publisher_is_rejected(self):
        self.assertEqual(PUBLISHER_POLICY["arcom.fr"]["source_type"], "official")
        entry = {
            "reported_publisher": "Arcom",
            "publisher_domain": "www.arcom.fr",
            "publisher": "Arcom",
            "headline": "Présidentielle 2027 : une décision",
            "summary": "",
            "url": "https://news.google.com/rss/articles/official",
            "canonical_url": "https://news.google.com/rss/articles/official",
            "feed_url": "https://news.google.com/rss/search?q=test",
            "published_at": datetime(2026, 7, 22, tzinfo=timezone.utc),
        }
        accepted, rejected = accept_discovery_entries([entry], "test-query")
        self.assertEqual(accepted, [])
        self.assertEqual(rejected[0]["rejection_reason"], "non_media_publisher")

    def test_contributing_publishers_count_is_media_only(self):
        policy = {
            "media.example": {
                "name": "Media Example",
                "source_type": "media",
                "tier": "core",
                "enabled": True,
            },
            "official.example": {
                "name": "Official Example",
                "source_type": "official",
                "tier": "core",
                "enabled": True,
            },
            "fact.example": {
                "name": "Fact Example",
                "source_type": "fact_check",
                "tier": "extended",
                "enabled": True,
            },
        }
        entries = [
            {
                "publisher": "Media Example",
                "source_id": "discovery:media",
            },
            {
                "publisher": "Official Example",
                "source_id": SOURCES[0]["source_id"],
            },
            {
                "publisher": "Fact Example",
                "source_id": "discovery:fact-check",
            },
            {
                "publisher": "Unknown Example",
                "source_id": "discovery:unknown",
            },
        ]
        self.assertEqual(
            count_contributing_media_publishers(entries, policy),
            1,
        )

    def test_publisher_suffix_removal_is_exact(self):
        for separator in ("-", "–", "—"):
            self.assertEqual(
                remove_publisher_suffix(
                    (
                        "Présidentielle 2027 : une actualité "
                        f"{separator} Le Monde"
                    ),
                    "Le Monde",
                ),
                "Présidentielle 2027 : une actualité",
            )
        self.assertEqual(
            remove_publisher_suffix(
                "Le Monde politique change",
                "Le Monde",
            ),
            "Le Monde politique change",
        )

    def test_direct_feed_precedence_and_deterministic_order(self):
        published_at = datetime(2026, 7, 22, 8, tzinfo=timezone.utc)
        shared_discovery = {
            "source_id": "discovery:test-query",
            "publisher": "BFMTV — Politique",
            "headline": "Présidentielle 2027 : une annonce",
            "url": "https://news.google.com/rss/articles/example",
            "canonical_url": "https://news.google.com/rss/articles/example",
            "published_at": published_at,
        }
        publisher_site = dict(shared_discovery)
        publisher_site.update(
            {
                "source_id": "publisher-site:bfmtv.com",
                "url": "https://news.google.com/rss/articles/site-example",
                "canonical_url": (
                    "https://news.google.com/rss/articles/site-example"
                ),
            }
        )
        direct = {
            "source_id": "bfmtv-politique",
            "publisher": "BFMTV — Politique",
            "headline": "Présidentielle 2027 : une annonce",
            "url": "https://www.bfmtv.com/politique/example.html",
            "canonical_url": "https://bfmtv.com/politique/example.html",
            "published_at": published_at,
        }
        first, first_stats = deduplicate_entries(
            [shared_discovery, publisher_site, direct]
        )
        second, second_stats = deduplicate_entries(
            [shared_discovery, publisher_site, direct]
        )
        self.assertEqual(first, second)
        self.assertEqual(first_stats, second_stats)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["source_id"], "bfmtv-politique")
        self.assertEqual(first_stats["direct_precedence_replacements"], 0)
        self.assertEqual(
            first_stats["publisher_site_precedence_replacements"],
            1,
        )
        self.assertEqual(
            first_stats["direct_over_publisher_site_replacements"],
            1,
        )
        self.assertEqual(first_stats["duplicates_removed"], 2)
        self.assertEqual(
            first_stats["removed_by_transport"]["shared_discovery"],
            1,
        )
        self.assertEqual(
            first_stats["removed_by_transport"]["publisher_site"],
            1,
        )

    def test_transport_priority_is_direct_then_site_then_shared(self):
        direct = {"source_id": "bfmtv-politique"}
        publisher_site = {"source_id": "publisher-site:bfmtv.com"}
        shared = {"source_id": "discovery:test-query"}

        self.assertEqual(entry_transport(direct), "direct")
        self.assertEqual(entry_transport(publisher_site), "publisher_site")
        self.assertEqual(entry_transport(shared), "shared_discovery")
        self.assertGreater(
            transport_priority(direct),
            transport_priority(publisher_site),
        )
        self.assertGreater(
            transport_priority(publisher_site),
            transport_priority(shared),
        )

    def test_direct_feed_replaces_retained_discovery_copy(self):
        generated_at = datetime(2026, 7, 22, 10, tzinfo=timezone.utc)
        discovery = self.inventory_entry(
            generated_at - timedelta(hours=2),
            headline="Présidentielle 2027 : une annonce",
        )
        discovery.update(
            {
                "source_id": "discovery:test-query",
                "publisher": "BFMTV — Politique",
                "url": "https://news.google.com/rss/articles/example",
                "canonical_url": "https://news.google.com/rss/articles/example",
            }
        )
        first, _entries, _stats = merge_inventory(
            {
                "schema_version": 3,
                "generated_at": None,
                "window_days": 30,
                "items": [],
            },
            [discovery],
            generated_at,
            30,
        )

        direct = dict(discovery)
        direct.update(
            {
                "source_id": "bfmtv-politique",
                "feed_url": "https://www.bfmtv.com/rss/politique/",
                "url": "https://www.bfmtv.com/politique/example.html",
                "canonical_url": "https://bfmtv.com/politique/example.html",
            }
        )
        second, entries, _stats = merge_inventory(
            first,
            [direct],
            generated_at + timedelta(hours=1),
            30,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["source_id"], "bfmtv-politique")
        self.assertEqual(second["items"][0]["source_id"], "bfmtv-politique")

    def test_build_wire_keeps_direct_source_contract_with_discovery(self):
        generated_at = datetime(2026, 7, 25, 13, tzinfo=timezone.utc)
        published = format_datetime(generated_at)
        request_count = 0
        request_count_lock = threading.Lock()
        direct_feed = f"""<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel><item>
          <title>Présidentielle 2027 : une alliance est annoncée</title>
          <link>https://example.test/direct-article</link>
          <pubDate>{published}</pubDate>
          <description>Une actualité sur la campagne présidentielle.</description>
        </item></channel></rss>""".encode("utf-8")
        discovery_feed = f"""<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel><item>
          <title>Présidentielle 2027 : une proposition - Le Monde</title>
          <link>https://news.google.com/rss/articles/discovery-example</link>
          <pubDate>{published}</pubDate>
          <description>Une proposition de campagne.</description>
          <source url='https://www.lemonde.fr'>Le Monde</source>
        </item></channel></rss>""".encode("utf-8")

        def fake_request(url, **_kwargs):
            nonlocal request_count
            with request_count_lock:
                request_count += 1
            if url.startswith("https://news.google.com/"):
                return successful_fetch(discovery_feed, url)
            return successful_fetch(direct_feed, url)

        with tempfile.TemporaryDirectory() as directory:
            polls_path = Path(directory) / "polls.json"
            polls_path.write_text(
                json.dumps(
                    {
                        "events": [
                            {
                                "round": "first_round",
                                "fieldwork_end": "2026-07-25",
                                "candidates": [
                                    {
                                        "name": (
                                            f"Candidate {index:02d}"
                                        )
                                    }
                                    for index in range(1, 21)
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            inventory_path = Path(directory) / "inventory.json"
            review_path = Path(directory) / "publishers.json"
            health_routes = []
            health_attempts = []
            with patch(
                "fetch_news_wire.fetch_news_route",
                side_effect=fake_request,
            ):
                payload, inventory = build_wire(
                    polls_path,
                    30,
                    0,
                    inventory_path,
                    review_path,
                    generated_at=generated_at,
                    health_route_configurations=health_routes,
                    health_attempts=health_attempts,
                )
                review = json.loads(
                    review_path.read_text(encoding="utf-8")
                )

        direct_source_count = len(SOURCES)
        self.assertEqual(len(payload["sources"]), direct_source_count)
        self.assertEqual(
            payload["counts"]["successful_sources"],
            direct_source_count,
        )
        candidate_count = len(payload["candidate_roster"]["names"])
        candidate_query_count = (candidate_count + 3) // 4
        enabled_static_query_count = sum(
            bool(query.get("enabled", True))
            for query in DISCOVERY_QUERIES
        )
        expected_discovery_query_count = (
            enabled_static_query_count + candidate_query_count
        )
        self.assertEqual(
            payload["discovery"]["configured_queries"],
            expected_discovery_query_count,
        )
        self.assertEqual(
            payload["discovery"]["successful_queries"],
            payload["discovery"]["configured_queries"],
        )
        self.assertEqual(
            payload["discovery"]["quarantined_items"],
            sum(
                query["quarantined_items"]
                for query in payload["discovery"]["queries"]
            ),
        )
        coverage = payload["feed_coverage"]
        self.assertEqual(coverage["direct_feeds"], direct_source_count)
        self.assertEqual(
            coverage["shared_discovery_feeds"],
            payload["discovery"]["configured_queries"],
        )
        self.assertEqual(coverage["publisher_site_feeds"], 180)
        self.assertEqual(
            coverage["configured_feeds"],
            (
                direct_source_count
                + coverage["shared_discovery_feeds"]
                + coverage["publisher_site_feeds"]
            ),
        )
        self.assertEqual(payload["discovery"]["quarantined_items"], 0)
        self.assertGreater(
            coverage["publisher_site_items_quarantined"],
            0,
        )
        self.assertTrue(all(
            "transports" in publisher
            for publisher in review["publishers"]
        ))
        self.assertTrue(any(
            "publisher_site" in publisher["transports"]
            for publisher in review["publishers"]
        ))
        hourly_feed_count = (
            direct_source_count
            + coverage["shared_discovery_feeds"]
        )
        self.assertEqual(
            coverage["feeds_due_this_run"],
            hourly_feed_count + coverage["publisher_site_feeds_due"],
        )
        self.assertEqual(
            coverage["feeds_successful_this_run"],
            (
                direct_source_count
                + payload["discovery"]["successful_queries"]
                + coverage["publisher_site_feeds_successful"]
            ),
        )
        due_health_routes = [
            route for route in health_routes if route["due_this_run"]
        ]
        self.assertEqual(len(health_attempts), len(due_health_routes))
        self.assertEqual(request_count, len(health_attempts))
        self.assertEqual(
            {attempt["route_id"] for attempt in health_attempts},
            {route["route_id"] for route in due_health_routes},
        )
        self.assertTrue(inventory["items"])
        visible_publishers = {
            item["publisher"] for item in payload["relevant_news"]
        }
        self.assertNotIn("Google News", visible_publishers)
        validate_output(payload)

        invalid = json.loads(json.dumps(payload))
        invalid["discovery"]["successful_queries"] -= 1
        with self.assertRaisesRegex(
            RuntimeError,
            "successful_queries does not match",
        ):
            validate_output(invalid)

        invalid = json.loads(json.dumps(payload))
        invalid["discovery"][
            "accepted_items_after_deduplication"
        ] = (
            invalid["discovery"][
                "accepted_items_before_deduplication"
            ] + 1
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "accepted item counts are inconsistent",
        ):
            validate_output(invalid)

        invalid = json.loads(json.dumps(payload))
        invalid["feed_coverage"]["configured_feeds"] -= 1
        with self.assertRaisesRegex(
            RuntimeError,
            "configured feed count is invalid",
        ):
            validate_output(invalid)

        invalid = json.loads(json.dumps(payload))
        invalid["discovery"]["quarantined_items"] += 1
        with self.assertRaisesRegex(
            RuntimeError,
            "quarantined item count does not match queries",
        ):
            validate_output(invalid)

        invalid = json.loads(json.dumps(payload))
        invalid_item = invalid["relevant_news"][0]
        invalid_item["candidates"] = ["Édouard Philippe"]
        invalid_item["candidate_matches"] = []
        with self.assertRaisesRegex(
            RuntimeError,
            "candidates disagree with candidate_matches",
        ):
            validate_output(invalid)

        reduced = json.loads(json.dumps(payload))
        reduced_site_feed = generate_publisher_site_feeds()[0]
        reduced_generated_at = datetime.fromisoformat(
            reduced["generated_at"].replace("Z", "+00:00")
        )
        reduced_due = int(
            publisher_site_feed_due(
                reduced_site_feed,
                reduced_generated_at,
            )
        )
        reduced["discovery"]["approved_media_domains"] = 1
        reduced_hourly_feed_count = (
            len(SOURCES)
            + reduced["feed_coverage"]["shared_discovery_feeds"]
        )
        reduced_successful_hourly_feed_count = (
            len(SOURCES)
            + reduced["discovery"]["successful_queries"]
        )
        reduced["feed_coverage"].update(
            {
                "configured_feeds": reduced_hourly_feed_count + 1,
                "publisher_site_feeds": 1,
                "publisher_site_feeds_due": reduced_due,
                "publisher_site_feeds_successful": 0,
                "configured_media_publishers": 1,
                "contributing_publishers_30d": 0,
                "feeds_due_this_run": (
                    reduced_hourly_feed_count + reduced_due
                ),
                "feeds_successful_this_run": (
                    reduced_successful_hourly_feed_count
                ),
            }
        )
        with patch(
            "fetch_news_wire.generate_publisher_site_feeds",
            return_value=[reduced_site_feed],
        ):
            validate_output(reduced)

        invalid = json.loads(json.dumps(payload))
        invalid["feed_coverage"]["publisher_site_feeds_due"] += 1
        invalid["feed_coverage"]["feeds_due_this_run"] += 1
        with self.assertRaisesRegex(
            RuntimeError,
            "publisher-site schedule count is invalid",
        ):
            validate_output(invalid)

    def test_build_wire_reports_empty_parses_as_successful_attempts(self):
        generated_at = datetime(2026, 7, 24, 8, tzinfo=timezone.utc)
        published = format_datetime(generated_at)
        first_source_url = SOURCES[0]["feed_url"]
        seen_fetch_options = {}
        populated_feed = f"""<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel><item>
          <title>Présidentielle 2027 : une alliance est annoncée</title>
          <link>https://example.test/one-current-item</link>
          <pubDate>{published}</pubDate>
          <description>Une actualité sur la campagne présidentielle.</description>
        </item></channel></rss>""".encode("utf-8")
        empty_feed = (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<rss version='2.0'><channel></channel></rss>"
        ).encode("utf-8")

        def fake_request(url, **kwargs):
            if url == first_source_url:
                seen_fetch_options.update(kwargs)
                return successful_fetch(populated_feed, url)
            return successful_fetch(empty_feed, url)

        health_routes = []
        health_attempts = []
        with patch(
            "fetch_news_wire.fetch_news_route",
            side_effect=fake_request,
        ):
            payload, _inventory = build_wire(
                Path("polls.json"),
                30,
                0,
                generated_at=generated_at,
                health_route_configurations=health_routes,
                health_attempts=health_attempts,
                previous_source_health={
                    "routes": [
                        {
                            "route_id": (
                                f"direct:{SOURCES[0]['source_id']}"
                            ),
                            "validator_url": first_source_url,
                            "etag": '"v1"',
                            "last_modified": (
                                "Wed, 22 Jul 2026 08:00:00 GMT"
                            ),
                        }
                    ]
                },
            )

        empty_attempts = [
            attempt
            for attempt in health_attempts
            if attempt["parsed_item_count"] == 0
        ]
        self.assertTrue(payload["relevant_news"])
        self.assertTrue(empty_attempts)
        self.assertTrue(all(
            attempt["success"] for attempt in empty_attempts
        ))
        self.assertTrue(all(
            attempt["failure_category"] is None
            for attempt in empty_attempts
        ))
        self.assertEqual(seen_fetch_options["etag"], '"v1"')
        self.assertEqual(
            seen_fetch_options["last_modified"],
            "Wed, 22 Jul 2026 08:00:00 GMT",
        )

    def test_not_modified_routes_skip_parsing_and_retain_inventory(self):
        generated_at = datetime(2026, 7, 24, 8, tzinfo=timezone.utc)
        source = SOURCES[0]
        retained_entry = self.inventory_entry(
            generated_at - timedelta(hours=2),
        )
        retained_entry.update(
            {
                "source_id": source["source_id"],
                "publisher": source["name"],
                "feed_url": source["feed_url"],
                "politics_specific": bool(
                    source.get("politics_specific")
                ),
            }
        )
        previous_inventory, _entries, _stats = merge_inventory(
            {
                "schema_version": 3,
                "generated_at": None,
                "window_days": 30,
                "items": [],
            },
            [retained_entry],
            generated_at - timedelta(hours=1),
            30,
        )
        request_count = 0

        def fake_fetch(url, **_kwargs):
            nonlocal request_count
            request_count += 1
            return not_modified_fetch(url)

        with tempfile.TemporaryDirectory() as directory:
            inventory_path = Path(directory) / "inventory.json"
            inventory_path.write_text(
                json.dumps(previous_inventory),
                encoding="utf-8",
            )
            health_routes = []
            health_attempts = []
            with (
                patch(
                    "fetch_news_wire.fetch_news_route",
                    side_effect=fake_fetch,
                ),
                patch(
                    "fetch_news_wire.parse_feed",
                    side_effect=AssertionError(
                        "304 response must not be parsed"
                    ),
                ),
            ):
                payload, inventory = build_wire(
                    Path("polls.json"),
                    30,
                    0,
                    inventory_path,
                    generated_at=generated_at,
                    health_route_configurations=health_routes,
                    health_attempts=health_attempts,
                )

        self.assertEqual(request_count, len(health_attempts))
        self.assertTrue(health_attempts)
        self.assertTrue(all(
            attempt["success"] and attempt["not_modified"]
            for attempt in health_attempts
        ))
        self.assertTrue(all(
            attempt["http_status"] == 304
            and attempt["parsed_item_count"] == 0
            for attempt in health_attempts
        ))
        self.assertEqual(len(inventory["items"]), 1)
        self.assertEqual(
            inventory["items"][0]["canonical_url"],
            retained_entry["canonical_url"],
        )
        self.assertEqual(len(payload["relevant_news"]), 1)

    def test_google_news_semaphore_preserves_deterministic_order(self):
        generated_at = datetime(2026, 7, 23, 8, tzinfo=timezone.utc)
        published = format_datetime(generated_at)
        lock = threading.Lock()
        active_google = 0
        max_active_google = 0

        def feed_bytes(url):
            token = str(abs(hash(url)) % 100000)
            if url.startswith("https://news.google.com/"):
                return f"""<?xml version='1.0' encoding='UTF-8'?>
                <rss version='2.0'><channel><item>
                  <title>Présidentielle 2027 : article {token} - Le Monde</title>
                  <link>https://news.google.com/rss/articles/{token}</link>
                  <pubDate>{published}</pubDate>
                  <description>Une proposition de campagne.</description>
                  <source url='https://www.lemonde.fr'>Le Monde</source>
                </item></channel></rss>""".encode("utf-8")
            return f"""<?xml version='1.0' encoding='UTF-8'?>
            <rss version='2.0'><channel><item>
              <title>Présidentielle 2027 : direct {token}</title>
              <link>https://example.test/direct-{token}</link>
              <pubDate>{published}</pubDate>
              <description>Une proposition de campagne.</description>
            </item></channel></rss>""".encode("utf-8")

        def fake_request(url, **_kwargs):
            nonlocal active_google, max_active_google
            is_google = url.startswith("https://news.google.com/")
            if is_google:
                with lock:
                    active_google += 1
                    max_active_google = max(max_active_google, active_google)
                time.sleep((abs(hash(url)) % 3 + 1) / 1000)
            try:
                body = feed_bytes(url)
                return successful_fetch(body, url)
            finally:
                if is_google:
                    with lock:
                        active_google -= 1

        results = []
        with patch(
            "fetch_news_wire.fetch_news_route",
            side_effect=fake_request,
        ):
            for _run in range(2):
                with tempfile.TemporaryDirectory() as directory:
                    payload, inventory = build_wire(
                        Path("polls.json"),
                        30,
                        0,
                        Path(directory) / "inventory.json",
                        Path(directory) / "publishers.json",
                        generated_at=generated_at,
                    )
                    results.append(
                        (
                            [item["id"] for item in payload["relevant_news"]],
                            [item["id"] for item in inventory["items"]],
                            payload["feed_coverage"],
                        )
                    )

        self.assertEqual(FETCH_WORKERS, 12)
        self.assertEqual(GOOGLE_NEWS_WORKERS, 4)
        self.assertLessEqual(max_active_google, GOOGLE_NEWS_WORKERS)
        self.assertEqual(results[0], results[1])

    def test_rss_summary_is_parsed_and_can_supply_election_context(self):
        raw = """<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel><item>
          <title>Le parti arrête son calendrier</title>
          <link>https://example.test/article</link>
          <pubDate>Wed, 22 Jul 2026 08:00:00 GMT</pubDate>
          <description>La primaire pour l'election presidentielle 2027 est fixee.</description>
        </item></channel></rss>""".encode("utf-8")
        entries = parse_feed(raw, "Example", "https://example.test/rss")
        self.assertEqual(len(entries), 1)
        combined = normalize(entries[0]["headline"] + " " + entries[0]["summary"])
        self.assertTrue(explicit_election_match(combined))

    def test_summary_legal_word_cannot_create_a_notable_change(self):
        headline = normalize(
            "Marine Le Pen ou le trumpisme à la française"
        )
        combined = normalize(
            "Marine Le Pen ou le trumpisme à la française. "
            "L’éditorial rappelle sa condamnation et sa candidature "
            "à la présidentielle."
        )
        result = classify_notable_development(
            combined,
            ["Marine Le Pen"],
            {"politics_specific": True},
            headline,
        )
        self.assertIsNone(result)

    def test_material_development_gate_accepts_actions_and_rejects_mentions(self):
        source = {"politics_specific": True}
        accepted = classify_notable_development(
            normalize(
                "Marine Le Pen reste eligible pour la presidentielle "
                "apres la decision de la Cour de cassation"
            ),
            ["Marine Le Pen"],
            source,
        )
        rejected = classify_notable_development(
            normalize("Marine Le Pen joue au golf avec Jordan Bardella"),
            ["Marine Le Pen", "Jordan Bardella"],
            source,
        )
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["id"], "legal_eligibility")
        self.assertIsNone(rejected)


    def test_notable_gate_rejects_unrelated_national_politics(self):
        source = {"politics_specific": True}
        rejected = [
            (
                "Protoxyde d azote rodeos urbains free parties le Parlement "
                "adopte definitivement le projet de loi Ripost de Laurent Nunez",
                ["Laurent Nuñez"],
            ),
            (
                "Finalement la ministre Monique Barbut decide de rester au "
                "gouvernement apres avoir vu Emmanuel Macron",
                ["Emmanuel Macron"],
            ),
            (
                "Interdiction des reseaux sociaux aux moins de 15 ans la loi "
                "vient d etre definitivement adoptee",
                ["Sébastien Lecornu"],
            ),
            (
                "Senatoriales dans les Bouches du Rhone Valerie Boyer se lance "
                "de son cote",
                ["Valérie Boyer"],
            ),
            (
                "France le senateur republicain Francois Noel Buffet nomme "
                "Defenseur des droits",
                ["François-Noël Buffet"],
            ),
        ]
        for headline, candidates in rejected:
            self.assertIsNone(
                classify_notable_development(
                    normalize(headline),
                    candidates,
                    source,
                    normalize(headline),
                ),
                headline,
            )

    def test_notable_gate_keeps_presidential_actions_and_candidate_legal_outcomes(self):
        source = {"politics_specific": True}
        accepted = [
            (
                "Presidentielle Francois Hollande se prepare a entrer en campagne",
                ["François Hollande"],
                "candidacies_endorsements",
            ),
            (
                "Marine Le Pen reste eligible pour la presidentielle apres "
                "la decision de la Cour de cassation",
                ["Marine Le Pen"],
                "legal_eligibility",
            ),
            (
                "Presidentielle le PS se prononce pour une primaire fermee",
                [],
                "selection_strategy",
            ),
            (
                "Presidentielle Marine Le Pen envisageant la piste d un "
                "referendum met la pression sur le Conseil constitutionnel",
                ["Marine Le Pen"],
                "positioning_integrity",
            ),
        ]
        for headline, candidates, expected in accepted:
            result = classify_notable_development(
                normalize(headline),
                candidates,
                source,
                normalize(headline),
            )
            self.assertIsNotNone(result, headline)
            self.assertEqual(result["id"], expected)

    def test_structured_electoral_support_rejects_ordinary_destinations(self):
        cases = [
            (
                "« Ces maisons détruites, ces animaux morts, ça fait "
                "forcément penser à des scènes de guerre » : président des "
                "maires de France, David Lisnard est allé au soutien des "
                "communes incendiées dans le Var",
                ["David Lisnard"],
            ),
            (
                "« Ces maisons détruites, ces animaux morts… Alors que ça "
                "fume encore, ça fait forcément penser à des scènes de "
                "guerre » : président des maires de France, David Lisnard "
                "est allé au soutien des communes incendiées dans le Var",
                ["David Lisnard"],
            ),
            ("David Lisnard est allé au soutien des communes incendiées", ["David Lisnard"]),
            ("Le candidat François Hollande apporte son soutien aux victimes", ["François Hollande"]),
            ("Le président François Hollande soutient les agriculteurs", ["François Hollande"]),
            ("François Hollande soutient une réforme", ["François Hollande"]),
            ("François Hollande apporte son soutien aux sinistrés", ["François Hollande"]),
            ("François Hollande apporte son soutien aux policiers", ["François Hollande"]),
            ("François Hollande apporte son soutien aux pompiers", ["François Hollande"]),
            ("Le soutien de David Lisnard aux pompiers", ["David Lisnard"]),
            ("Les élus soutenus par David Lisnard après l'incendie", ["David Lisnard"]),
            ("François Hollande appelle à voter pour une réforme", ["François Hollande"]),
            ("Marine Le Pen soutient les agriculteurs à l’approche de la présidentielle", ["Marine Le Pen"]),
            ("David Lisnard apporte son soutien aux communes pendant la campagne présidentielle", ["David Lisnard"]),
            ("Édouard Philippe soutient une réforme pour l’élection présidentielle", ["Édouard Philippe"]),
            ("X soutient les victimes avant le second tour", ["X"]),
            ("X se rallie aux agriculteurs avant la présidentielle", ["X"]),
            ("X appelle à voter pour une réforme à la présidentielle", ["X"]),
            ("X apporte son soutien à une campagne de vaccination", ["X"]),
            ("X apporte son appui à une campagne associative avant l’élection", ["X"]),
            ("X soutient une coalition humanitaire pendant la présidentielle", ["X"]),
        ]

        for headline, candidates in cases:
            normalized = normalize(headline)
            candidate_matches = match_news_candidates(normalized, "", candidates)
            evidence = classify_structured_electoral_support(normalized, candidates)
            with self.subTest(headline=headline):
                self.assertEqual(evidence["matched_terms"], [])
                self.assertIsNone(
                    classify_relevant_news(
                        normalized,
                        "",
                        candidates,
                        candidate_matches,
                    )
                )
                self.assertIsNone(
                    classify_notable_development(
                        normalized,
                        candidates,
                        {"politics_specific": True},
                        normalized,
                        candidate_matches,
                    )
                )

    def test_structured_electoral_support_accepts_electoral_destinations(self):
        cases = [
            ("François Hollande annonce son soutien à la candidature présidentielle de Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande soutient la candidature présidentielle de Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("Le Parti socialiste apporte son soutien au candidat à la présidentielle", []),
            ("François Hollande se rallie à Raphaël Glucksmann pour la présidentielle", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande officialise son ralliement à Raphaël Glucksmann pour la présidentielle", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande appelle à voter pour Raphaël Glucksmann au second tour de la présidentielle", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande soutient Raphaël Glucksmann au second tour de la présidentielle", ["François Hollande", "Raphaël Glucksmann"]),
            ("Le soutien d'Elon Musk au RN relance la campagne présidentielle de Marine Le Pen", ["Marine Le Pen"]),
            ('"Marine Le Pen est le dernier espoir de la France": le soutien d\'Elon Musk à la candidature présidentielle de Marine Le Pen provoque des accusations d\'"ingérence étrangère"', ["Marine Le Pen"]),
            ("Les élus RN de la région dieppoise au soutien de la candidature présidentielle de Marine Le Pen", ["Marine Le Pen"]),
            ("Le soutien de François Hollande à la candidature présidentielle de Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("Le ralliement de François Hollande à Marine Le Pen pour la présidentielle", ["François Hollande", "Marine Le Pen"]),
            ("François Hollande apporte son soutien à la campagne présidentielle de Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande apporte son soutien à la campagne de Raphaël Glucksmann pour 2027", ["François Hollande", "Raphaël Glucksmann"]),
            ("Le Parti socialiste apporte son soutien à la campagne présidentielle du candidat", []),
        ]

        for headline, candidates in cases:
            normalized = normalize(headline)
            candidate_matches = match_news_candidates(normalized, "", candidates)
            evidence = classify_structured_electoral_support(normalized, candidates)
            relevance = classify_relevant_news(
                normalized,
                "",
                candidates,
                candidate_matches,
            )
            with self.subTest(headline=headline):
                self.assertTrue(evidence["matched_terms"])
                self.assertIsNotNone(relevance)
                self.assertIn(
                    relevance["reason"],
                    {"campaign_or_selection_context", "presidential_context"},
                )

    def test_nice_matin_candidate_provenance_survives_relevance_rejection(self):
        headline = (
            "« Ces maisons détruites, ces animaux morts, ça fait forcément "
            "penser à des scènes de guerre » : président des maires de "
            "France, David Lisnard est allé au soutien des communes "
            "incendiées dans le Var"
        )
        normalized = normalize(headline)
        candidate_matches = match_news_candidates(
            normalized,
            normalized,
            ["David Lisnard"],
        )
        self.assertEqual(
            candidate_matches,
            [{
                "candidate": "David Lisnard",
                "matched_aliases": ["david lisnard"],
                "locations": ["headline", "summary"],
            }],
        )
        relevance = classify_relevant_news(
            normalized,
            normalized,
            ["David Lisnard"],
            candidate_matches,
        )
        development = classify_notable_development(
            normalized,
            ["David Lisnard"],
            {"politics_specific": True},
            normalized,
            candidate_matches,
        )
        self.assertIsNone(relevance)
        self.assertIsNone(development)
        self.assertEqual(current_presidential_matches(normalized), [])
        self.assertEqual(
            classify_candidate_coverage_scope(
                is_election_news=False,
                relevance=relevance,
                development=development,
            ),
            "general",
        )

    def test_broad_relevance_rejects_generic_candidate_commentary(self):
        headline = normalize("Marine Le Pen ou le trumpisme à la française")
        matches = match_news_candidates(
            headline,
            "",
            ["Marine Le Pen"],
        )
        result = classify_relevant_news(
            headline,
            normalize("Un éditorial analyse son positionnement politique."),
            ["Marine Le Pen"],
            matches,
        )
        self.assertTrue(matches)
        self.assertIsNone(result)

    def test_bounded_counterfactual_presidential_positioning(self):
        accepted = [
            (
                "Gabriel Attal promet un plan massif sur l'eau s'il est élu",
                ["Gabriel Attal"],
            ),
            (
                "Gabriel Attal souhaite réformer les institutions s'il est "
                "élu en 2027",
                ["Gabriel Attal"],
            ),
            (
                "Décentralisation, justice, immigration : Gabriel Attal "
                "promet la plus grande réforme institutionnelle depuis "
                "1958 s'il est élu",
                ["Gabriel Attal"],
            ),
            (
                "Marine Tondelier détaille son programme si elle est élue",
                ["Marine Tondelier"],
            ),
            (
                "Marine Tondelier propose un référendum si elle est élue "
                "en 2027",
                ["Marine Tondelier"],
            ),
            (
                "Place à la nouvelle France : si Jean-Luc Mélenchon "
                "devenait président",
                ["Jean-Luc Mélenchon"],
            ),
            (
                "Édouard Philippe assure qu'il serait le président d'une "
                "France qui maîtrise son destin",
                ["Édouard Philippe"],
            ),
            (
                "Pour sa rentrée, François Hollande veut prouver qu'il est "
                "prêt à être le recours en 2027",
                ["François Hollande"],
            ),
        ]
        rejected = [
            (
                "Municipales : Gabriel Attal promet un plan s'il est élu",
                ["Gabriel Attal"],
            ),
            (
                "Gabriel Attal rencontre les élus de Bretagne",
                ["Gabriel Attal"],
            ),
            (
                "Gabriel Attal raconte ses vacances s'il est élu par le jury",
                ["Gabriel Attal"],
            ),
            (
                "François Hollande évoque un recours en justice en 2027",
                ["François Hollande"],
            ),
        ]

        for headline, candidates in accepted:
            matches = match_news_candidates(headline, "", candidates)
            with self.subTest(headline=headline):
                result = classify_relevant_news(
                    headline,
                    "",
                    candidates,
                    matches,
                )
                self.assertIsNotNone(result)
                self.assertTrue(
                    {
                        "elected_president_positioning",
                        "implicit_2027_positioning",
                    }
                    & set(result["matched_terms"])
                )

        for headline, candidates in rejected:
            matches = match_news_candidates(headline, "", candidates)
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_relevant_news(
                        headline,
                        "",
                        candidates,
                        matches,
                    )
                )

    def test_high_specificity_campaign_relationships_are_bounded(self):
        accepted = [
            (
                "Gabriel Attal accélère sa campagne, mais patine dans les "
                "sondages",
                ["Gabriel Attal"],
            ),
            (
                "Il y a une part de sacrifice : Franck Robine va diriger "
                "la campagne de Bruno Retailleau",
                ["Bruno Retailleau"],
            ),
            (
                "Quel rôle pour Jordan Bardella dans la campagne de Marine "
                "Le Pen ?",
                ["Marine Le Pen"],
            ),
            (
                "Gabriel Attal en escale à Vannes pour clore son Tro Breizh "
                "de campagne",
                ["Gabriel Attal"],
            ),
            (
                "François Ruffin, le candidat qui rêvait d'arriver à "
                "l'Élysée en auto-stop",
                ["François Ruffin"],
            ),
            (
                "Au RN, la candidature de Marine Le Pen rebat les cartes",
                ["Marine Le Pen"],
            ),
            (
                "SONDAGE EXCLUSIF - Édouard Philippe et Gabriel Attal au "
                "coude-à-coude dans l'opinion",
                ["Édouard Philippe", "Gabriel Attal"],
            ),
            (
                "Gabriel Attal dévoile son programme présidentiel",
                ["Gabriel Attal"],
            ),
            (
                "L'idée, c'est vraiment de faire campagne : Gabriel Attal, "
                "un été pied au plancher",
                ["Gabriel Attal"],
            ),
            (
                "L'édito du 10 août. En campagne, Gabriel Attal joue les "
                "acrobates",
                ["Gabriel Attal"],
            ),
        ]
        rejected = [
            (
                "Gabriel Attal commente une campagne de vaccination",
                ["Gabriel Attal"],
            ),
            (
                "Gabriel Attal est en campagne de sensibilisation à la "
                "vaccination",
                ["Gabriel Attal"],
            ),
            (
                "Sondage de popularité : Gabriel Attal reste apprécié",
                ["Gabriel Attal"],
            ),
            (
                "La stratégie de Jean-Luc Mélenchon sur la dette",
                ["Jean-Luc Mélenchon"],
            ),
            (
                "Le directeur de cabinet de Bruno Retailleau est nommé",
                ["Bruno Retailleau"],
            ),
            (
                "Marie-Claire Carrère-Gée : la droite doit faire campagne "
                "sur le gaullisme social",
                [],
            ),
            (
                "Réduction du nombre de parlementaires : Gabriel Attal "
                "reprend une promesse de campagne d'Emmanuel Macron faite "
                "en 2017",
                ["Gabriel Attal"],
            ),
        ]

        for headline, candidates in accepted:
            matches = match_news_candidates(headline, "", candidates)
            with self.subTest(headline=headline):
                self.assertIsNotNone(
                    classify_relevant_news(
                        headline,
                        "",
                        candidates,
                        matches,
                    )
                )

        for headline, candidates in rejected:
            matches = match_news_candidates(headline, "", candidates)
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_relevant_news(
                        headline,
                        "",
                        candidates,
                        matches,
                    )
                )

    def test_election_interference_requires_a_bounded_race_relationship(self):
        accepted = [
            (
                "Il faut s'attendre à une ingérence du Kremlin pour certains "
                "candidats en 2027, affirme Gabriel Attal",
                ["Gabriel Attal"],
            ),
            (
                "Interventions russes en 2027 : il y aura de l'ingérence "
                "pour certains candidats, affirme Gabriel Attal",
                ["Gabriel Attal"],
            ),
            (
                "Gabriel Attal accuse Moscou de vouloir voler l'élection "
                "aux Français",
                ["Gabriel Attal"],
            ),
            (
                "En 2027, les ingérences seront massives, prévient Raphaël "
                "Glucksmann",
                ["Raphaël Glucksmann"],
            ),
            (
                "Les ingérences russes s'invitent dans la campagne de 2027 "
                ": faut-il médiatiser les fake news visant les candidats ?",
                [],
            ),
            (
                "Face aux ingérences étrangères, que proposent les partis "
                "politiques, à huit mois de l'élection présidentielle ?",
                [],
            ),
        ]
        rejected = [
            (
                "Raphaël Glucksmann visé par une opération de "
                "désinformation russe",
                ["Raphaël Glucksmann"],
            ),
            (
                "Ingérence russe dans une élection américaine en 2028",
                [],
            ),
        ]

        for headline, candidates in accepted:
            matches = match_news_candidates(headline, "", candidates)
            with self.subTest(headline=headline):
                result = classify_relevant_news(
                    headline,
                    "",
                    candidates,
                    matches,
                )
                self.assertIsNotNone(result)
                self.assertIn("election_integrity", result["matched_terms"])

        for headline, candidates in rejected:
            matches = match_news_candidates(headline, "", candidates)
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_relevant_news(
                        headline,
                        "",
                        candidates,
                        matches,
                    )
                )

    def test_legal_developments_require_independent_race_qualification(self):
        rejected = [
            (
                "Affaire des statuettes : Dominique de Villepin entendu par "
                "le parquet national financier",
                "",
                ["Dominique de Villepin"],
            ),
            (
                "Visé par une enquête pour détournement de fonds publics, "
                "Édouard Philippe échoue à faire annuler le statut de la "
                "lanceuse d'alerte",
                "Le candidat à la présidentielle est visé par une enquête.",
                ["Édouard Philippe"],
            ),
            (
                "Raphaël Glucksmann confirme avoir porté plainte après une "
                "ingérence russe",
                "Une plainte a été déposée.",
                ["Raphaël Glucksmann"],
            ),
            (
                "Enquête financière sur les statuettes de Napoléon : "
                "Dominique de Villepin dans la tourmente à un an de la "
                "présidentielle",
                "",
                ["Dominique de Villepin"],
            ),
        ]
        accepted = [
            (
                "Marine Le Pen se pourvoit en cassation, la menace du "
                "bracelet électronique s'éloigne avant 2027",
                "",
                ["Marine Le Pen"],
            ),
            (
                "Gabriel Attal porte plainte après des ingérences étrangères",
                "La plainte vise des manipulations susceptibles de porter "
                "atteinte à la sincérité du scrutin présidentiel à venir.",
                ["Gabriel Attal"],
            ),
        ]

        for headline, summary, candidates in rejected:
            matches = match_news_candidates(headline, summary, candidates)
            combined = normalize(f"{headline} {summary}")
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_notable_development(
                        combined,
                        candidates,
                        {"politics_specific": True},
                        normalize(headline),
                        matches,
                    )
                )

        for headline, summary, candidates in accepted:
            matches = match_news_candidates(headline, summary, candidates)
            combined = normalize(f"{headline} {summary}")
            with self.subTest(headline=headline):
                result = classify_notable_development(
                    combined,
                    candidates,
                    {"politics_specific": True},
                    normalize(headline),
                    matches,
                )
                self.assertIsNotNone(result)
                self.assertEqual(result["id"], "legal_eligibility")

    def test_historical_and_foreign_subject_guards_are_bounded(self):
        rejected = [
            (
                "Retour sur les campagnes présidentielles",
                "Retour sur les campagnes présidentielles.",
            ),
            (
                "Visites présidentielles à Aix-en-Provence : quand VGE "
                "menait campagne pour sa réélection",
                "Une page d'histoire locale.",
            ),
            (
                "Giscard à la barre : une campagne qui impose un nouveau "
                "style en politique",
                "Mémoire avant l'élection de 2027. Aujourd'hui, retour en "
                "1974 avec Valéry Giscard d'Estaing.",
            ),
            (
                "Rob Sand, le démocrate qui veut reprendre l'Iowa au Parti "
                "républicain",
                "L'Iowa a voté Trump aux trois dernières élections "
                "présidentielles; Rob Sand vise le poste de gouverneur.",
            ),
            (
                "Élection présidentielle : quels étaient les résultats en "
                "2022 en France et dans votre commune",
                "Une page de résultats historiques.",
            ),
        ]
        accepted = [
            (
                "Présidentielle 2027 : les leçons de la campagne de 1974",
                "Une comparaison historique avec la course actuelle.",
            ),
            (
                "Ce que la victoire américaine pourrait changer pour la "
                "présidentielle française de 2027",
                "Une analyse de la campagne française.",
            ),
            (
                "Ingérences étrangères : faut-il interdire la plateforme X ?",
                "Une campagne de désinformation vise des personnalités en "
                "lice pour la présidentielle française de 2027.",
            ),
        ]

        for headline, summary in rejected:
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_relevant_news(headline, summary, [])
                )

        for headline, summary in accepted:
            with self.subTest(headline=headline):
                self.assertIsNotNone(
                    classify_relevant_news(headline, summary, [])
                )

    def test_race_year_timing_and_french_institution_anchors_are_bounded(self):
        accepted = [
            (
                "Sondages 2027 : Le Pen solide et possible percée à gauche",
                "",
            ),
            (
                "Renaissance cherche une candidature unique pour 2027",
                "",
            ),
            (
                "Présidentielle : le premier débat pour 2027 aura lieu en "
                "septembre",
                "",
            ),
            (
                "À neuf mois de la présidentielle, qui sont les candidats "
                "à gauche ?",
                "",
            ),
            (
                "Présidentielle : faut-il rendre anonymes les 500 "
                "parrainages ?",
                "",
            ),
            (
                "Banque de la démocratie : comment Matignon veut lutter "
                "contre les ingérences dans la campagne présidentielle",
                "",
            ),
            (
                "Storm-1516 : ingérence en vue de la campagne de 2027, "
                "quel mode opératoire ?",
                "",
            ),
            (
                "Présidentielle : l'ingérence russe, alibi ou vraie "
                "menace ?",
                "",
            ),
            (
                "Des faux comptes pilotés depuis l'Iran amplifient les "
                "fractures politiques françaises",
                "Ces opérations de désinformation visent l'élection "
                "présidentielle.",
            ),
            (
                "Xavier Bertrand défend sa candidature à l'Élysée",
                "",
            ),
            (
                "Bruno Le Maire ne ferme pas la porte à une candidature "
                "à la présidentielle",
                "",
            ),
            (
                "Présidentielle : le gouvernement négocie avec les banques "
                "pour faciliter le financement des candidats",
                "Les banques françaises cherchent à financer la campagne "
                "présidentielle des candidats.",
            ),
        ]
        rejected = [
            ("Budget 2027 : les arbitrages commencent", ""),
            (
                "Aircalin dévoile son programme de vols pour 2026/2027",
                "",
            ),
            (
                "Ouverture de l'appel à candidature pour la saison 2027",
                "",
            ),
            (
                "Le col du Granon candidat pour une étape en 2027",
                "",
            ),
            (
                "Vers une campagne antiraciste pour 2027",
                "",
            ),
            ("Une campagne de publicité adopte un nouveau mode", ""),
            (
                "Donald Trump relance sa campagne présidentielle",
                "",
            ),
            (
                "Rob Sand veut reprendre l'Iowa au Parti républicain",
                "Les élections présidentielles américaines sont évoquées.",
            ),
            (
                "Brésil : à trois mois de la présidentielle, la campagne "
                "se tend",
                "",
            ),
            (
                "Roumanie : des faux comptes visent l'élection "
                "présidentielle",
                "",
            ),
            (
                "Brésil : Flavio Bolsonaro annonce sa candidature à la "
                "présidentielle",
                "",
            ),
            (
                "Raphaël Glucksmann visé par des fake news russes",
                "Le candidat était en déplacement sans lien électoral.",
            ),
        ]

        for headline, summary in accepted:
            with self.subTest(headline=headline):
                self.assertIsNotNone(
                    classify_relevant_news(headline, summary, [])
                )

        for headline, summary in rejected:
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_relevant_news(headline, summary, [])
                )

        festival_headline = (
            "Politique : Avignon, le festival aussi des prétendants à la "
            "présidentielle, dont Dominique de Villepin"
        )
        festival_result = classify_relevant_news(
            festival_headline,
            "",
            ["Dominique de Villepin"],
            match_news_candidates(
                festival_headline,
                "",
                ["Dominique de Villepin"],
            ),
        )
        self.assertIsNotNone(festival_result)

        self.assertIsNone(
            classify_relevant_news(
                "Dominique de Villepin assiste au Festival d'Avignon",
                "",
                ["Dominique de Villepin"],
                match_news_candidates(
                    "Dominique de Villepin assiste au Festival d'Avignon",
                    "",
                    ["Dominique de Villepin"],
                ),
            )
        )

    def test_current_campaign_material_is_not_a_lifestyle_false_negative(self):
        headline = (
            "À quelques mois de l'élection présidentielle, Renaissance et "
            "LFI misent sur les cahiers de vacances pour faire campagne"
        )
        summary = (
            "Le PC et le PS ont déjà tenté l'expérience par le passé."
        )
        result = classify_relevant_news(headline, summary, [], [])
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "presidential_context")

        explicit_2027 = classify_relevant_news(
            "Présidentielle 2027 : un ancien joueur de l'équipe de France "
            "de football se rapproche de David Lisnard",
            "",
            ["David Lisnard"],
            match_news_candidates(
                "Présidentielle 2027 : un ancien joueur de l'équipe de "
                "France de football se rapproche de David Lisnard",
                "",
                ["David Lisnard"],
            ),
        )
        self.assertIsNotNone(explicit_2027)

    def test_routine_title_can_use_bounded_strategy_summary(self):
        headline = (
            "Pour l'ex-Premier ministre Gabriel Attal, l'occasion manquée "
            "d'un duel avec Jordan Bardella"
        )
        summary = (
            "Marine Le Pen va porter les couleurs du Rassemblement national "
            "à la présidentielle de 2027, Jordan Bardella reprenant son rôle "
            "de numéro 2 dans la campagne. Ce n'est pas une bonne nouvelle "
            "pour Gabriel Attal, qui espérait un duel."
        )
        candidates = ["Gabriel Attal", "Marine Le Pen"]
        result = classify_relevant_news(
            headline,
            summary,
            candidates,
            match_news_candidates(headline, summary, candidates),
        )
        self.assertIsNotNone(result)
        self.assertEqual(
            result["reason"],
            "summary_confirmed_presidential_context",
        )

        label_only = classify_relevant_news(
            "Gabriel Attal appelle les distributeurs à plafonner les prix "
            "des carburants",
            "Gabriel Attal, candidat Renaissance à l'élection "
            "présidentielle et ancien Premier ministre, était en direct.",
            ["Gabriel Attal"],
            match_news_candidates(
                "Gabriel Attal appelle les distributeurs à plafonner les "
                "prix des carburants",
                "Gabriel Attal, candidat Renaissance à l'élection "
                "présidentielle et ancien Premier ministre, était en direct.",
                ["Gabriel Attal"],
            ),
        )
        self.assertIsNone(label_only)

        campaign_trip = classify_relevant_news(
            "Salaires : Gabriel Attal alerte sur un nouveau mouvement des "
            "Gilets jaunes",
            "Le candidat à la présidentielle 2027 s'exprime lors d'un "
            "déplacement de campagne à Landerneau.",
            ["Gabriel Attal"],
            match_news_candidates(
                "Salaires : Gabriel Attal alerte sur un nouveau mouvement "
                "des Gilets jaunes",
                "Le candidat à la présidentielle 2027 s'exprime lors d'un "
                "déplacement de campagne à Landerneau.",
                ["Gabriel Attal"],
            ),
        )
        self.assertIsNotNone(campaign_trip)

        campaign_finance = classify_relevant_news(
            "Pourquoi Sébastien Lecornu s'intéresse au financement de la "
            "campagne de Marine Le Pen",
            "Les banques évoquent le financement de la campagne "
            "présidentielle de la candidate du Rassemblement national.",
            ["Marine Le Pen"],
            match_news_candidates(
                "Pourquoi Sébastien Lecornu s'intéresse au financement de "
                "la campagne de Marine Le Pen",
                "Les banques évoquent le financement de la campagne "
                "présidentielle de la candidate du Rassemblement national.",
                ["Marine Le Pen"],
            ),
        )
        self.assertIsNotNone(campaign_finance)


    def test_summary_candidate_labels_do_not_override_headline_subject(self):
        cases = [
            (
                "Visé par une enquête pour détournement de fonds publics, "
                "Édouard Philippe échoue à faire annuler le statut de la "
                "lanceuse d'alerte",
                "Le candidat à la présidentielle est visé par une enquête "
                "sans conséquence établie sur son éligibilité.",
                ["Édouard Philippe"],
            ),
            (
                "L'ancien conseiller de Gabriel Attal révèle son addiction "
                "passée à la cocaïne",
                "Le portrait revient sur celui qui a accompagné l'actuel "
                "candidat à la présidentielle pendant plusieurs années.",
                ["Gabriel Attal"],
            ),
            (
                "Jérôme Karsenti : Marine Le Pen a bafoué les principes "
                "démocratiques",
                "La candidature de la cheffe de file du RN s'inscrit dans "
                "une époque de banalisation de la corruption.",
                ["Marine Le Pen"],
            ),
        ]

        for headline, summary, candidates in cases:
            matches = match_news_candidates(headline, summary, candidates)
            with self.subTest(headline=headline):
                self.assertTrue(matches)
                self.assertIsNone(
                    classify_relevant_news(
                        headline,
                        summary,
                        candidates,
                        matches,
                    )
                )


    def test_summary_cannot_rescue_historical_presidential_subject(self):
        headline = "L'été d'avant présidentielle : en 1994, Balladur président"
        summary = (
            "Ségolène Royal préparait alors sa candidature à l'élection "
            "présidentielle."
        )
        candidates = ["Ségolène Royal"]

        self.assertIsNone(
            classify_relevant_news(
                headline,
                summary,
                candidates,
                match_news_candidates(headline, summary, candidates),
            )
        )

        self.assertIsNone(
            classify_relevant_news(
                "La France pour tous : la campagne où Jacques Chirac "
                "a croqué la pomme",
                "Cet été, retour sur les slogans des élections "
                "présidentielles. Aujourd'hui, l'élection de 1995, "
                "avec Jacques Chirac.",
                [],
            )
        )


    def test_summary_can_establish_presidential_policy_relationship(self):
        cases = [
            (
                "Gabriel Attal présente un plan massif sur l'eau",
                "Gabriel Attal, candidat à la présidentielle, explique ce "
                "qu'il mettrait en œuvre s'il était élu.",
                ["Gabriel Attal"],
            ),
            (
                "Édouard Philippe propose de limiter les régularisations",
                "Le candidat à l'élection présidentielle de 2027 inscrit "
                "cette mesure dans son programme.",
                ["Édouard Philippe"],
            ),
        ]

        for headline, summary, candidates in cases:
            matches = match_news_candidates(headline, summary, candidates)
            with self.subTest(headline=headline):
                self.assertIsNotNone(
                    classify_relevant_news(
                        headline,
                        summary,
                        candidates,
                        matches,
                    )
                )


    def test_current_corpus_candidate_identity_only_does_not_create_race_relevance(self):
        cases = [
            (
                "Enquêtes pour violences sexuelles sur mineurs : "
                "Libération publie la note qui met Gérald Darmanin dans l'embarras",
                ["Gérald Darmanin"],
            ),
            (
                "Pénurie de lunettes pour l'éclipse : "
                "Marine Tondelier dénonce un fiasco de santé publique",
                ["Marine Tondelier"],
            ),
            (
                "Jean-Luc Mélenchon, l'apprenti sorcier de la dette",
                ["Jean-Luc Mélenchon"],
            ),
            (
                "David Lisnard et la fin de l'État-Providence : "
                "un diagnostic radical, mais quelles solutions ?",
                ["David Lisnard"],
            ),
            (
                "Crise migratoire : pourquoi Xavier Bertrand veut "
                "un traité de Calais pour l'Europe ?",
                ["Xavier Bertrand"],
            ),
            (
                "30 millions de lunettes en 1999, pénurie en 2026 : "
                "Marine Tondelier et Nathalie Arthaud s'indignent avant l'éclipse",
                ["Marine Tondelier", "Nathalie Arthaud"],
            ),
        ]

        for headline, candidates in cases:
            matches = match_news_candidates(
                headline,
                "",
                candidates,
            )
            with self.subTest(headline=headline):
                self.assertTrue(matches)
                self.assertIsNone(
                    classify_relevant_news(
                        headline,
                        "",
                        candidates,
                        matches,
                    )
                )

    def test_broad_relevance_rejects_candidate_lifestyle(self):
        result = classify_relevant_news(
            normalize("Marine Le Pen joue au golf avec Jordan Bardella"),
            "",
            ["Marine Le Pen", "Jordan Bardella"],
        )
        self.assertIsNone(result)

    def test_broad_relevance_rejects_routine_government_and_legislation(self):
        rejected = [
            (
                "Finalement la ministre Monique Barbut reste au gouvernement "
                "après avoir vu Emmanuel Macron",
                ["Emmanuel Macron"],
            ),
            (
                "Aide à mourir Olivier Falorni présente le calendrier de la loi",
                ["Olivier Falorni"],
            ),
            (
                "Sénatoriales Valérie Boyer annonce sa candidature",
                ["Valérie Boyer"],
            ),
        ]
        for headline, candidates in rejected:
            self.assertIsNone(
                classify_relevant_news(
                    normalize(headline),
                    "",
                    candidates,
                ),
                headline,
            )

    def test_broad_relevance_rejects_weak_presidential_false_positives(self):
        rejected = [
            (
                "Emmanuel Macron accueille Ursula von der Leyen a l Elysee",
                "Une rencontre a la presidence de la Republique.",
                [],
            ),
            (
                "Monique Barbut symbole de la desillusion ecologique sous Macron",
                "Le gouvernement prepare le budget 2027.",
                ["Emmanuel Macron"],
            ),
            (
                "Budget 2027 le gouvernement esquisse ses priorites",
                "Le chef de l Etat recevra les ministres a l Elysee.",
                [],
            ),
            (
                "Aide a mourir deux ans de debats et trois gouvernements",
                "Le texte pourrait peser avant la presidentielle 2027.",
                ["Sébastien Lecornu"],
            ),
            (
                "Affaire Balogun la Fifa est verolee de trumpisme",
                "Une controverse pendant la Coupe du monde de football.",
                [],
            ),
            (
                "Presidentielle 2012 la victoire du president normal",
                "Retour historique sur Francois Hollande.",
                ["François Hollande"],
            ),
            (
                "Presidentielle 2007 le duel Sarko Sego",
                "Archive politique.",
                [],
            ),
        ]
        for headline, summary, candidates in rejected:
            self.assertIsNone(
                classify_relevant_news(
                    normalize(headline),
                    normalize(summary),
                    candidates,
                ),
                headline,
            )

    def test_broad_relevance_keeps_current_race_analysis_and_summary_confirmation(self):
        accepted = [
            (
                "Presidentielle pour Bernard Cazeneuve LFI n est pas en situation de gouverner",
                "",
                ["Bernard Cazeneuve"],
            ),
            (
                "Pour 2027 Jean-Luc Mélenchon tend la main aux Ecologistes",
                "La proposition concerne la prochaine presidentielle.",
                ["Jean-Luc Mélenchon"],
            ),
            (
                "Le Parti socialiste arrete son calendrier",
                "La primaire doit designer son candidat a l election presidentielle de 2027.",
                [],
            ),
        ]
        for headline, summary, candidates in accepted:
            self.assertIsNotNone(
                classify_relevant_news(
                    normalize(headline),
                    normalize(summary),
                    candidates,
                ),
                headline,
            )

    def test_broad_relevance_accepts_campaign_and_party_selection(self):
        accepted = [
            (
                "Entretien avec François Hollande sur ses ambitions présidentielles pour 2027",
                "",
                ["François Hollande"],
            ),
            (
                "Le Parti socialiste débat de sa primaire",
                "La formation prépare la présidentielle de 2027.",
                [],
            ),
            (
                "Marine Le Pen détaille sa stratégie",
                "La candidate prépare sa campagne présidentielle.",
                ["Marine Le Pen"],
            ),
        ]
        for headline, summary, candidates in accepted:
            self.assertIsNotNone(
                classify_relevant_news(
                    normalize(headline),
                    normalize(summary),
                    candidates,
                ),
                headline,
            )

    def test_broad_relevance_summary_can_confirm_presidential_context(self):
        result = classify_relevant_news(
            normalize("Le parti arrête son calendrier"),
            normalize(
                "La primaire doit désigner son candidat à l'élection "
                "présidentielle de 2027."
            ),
            [],
        )
        self.assertIsNotNone(result)
        self.assertEqual(
            result["reason"],
            "summary_confirmed_presidential_context",
        )

    def test_long_lcp_retrospective_is_rejected_but_keeps_candidates(self):
        headline = (
            "Hommage de La France insoumise à Robespierre: "
            "pourquoi ça fait débat"
        )
        summary = lcp_retrospective_summary()
        candidates = ["Jean-Luc Mélenchon", "Raphaël Glucksmann"]
        matches = match_news_candidates(headline, summary, candidates)

        self.assertEqual(len(summary), 3232)
        self.assertEqual(
            matches,
            [
                {
                    "candidate": "Jean-Luc Mélenchon",
                    "matched_aliases": ["jean luc melenchon"],
                    "locations": ["summary"],
                },
                {
                    "candidate": "Raphaël Glucksmann",
                    "matched_aliases": ["raphael glucksmann"],
                    "locations": ["summary"],
                },
            ],
        )
        relevance = classify_relevant_news(
            headline,
            summary,
            candidates,
            matches,
        )
        development = classify_notable_development(
            normalize(f"{headline} {summary}"),
            candidates,
            {"politics_specific": True},
            normalize(headline),
            matches,
        )

        self.assertIsNone(relevance)
        self.assertIsNone(development)
        self.assertEqual(
            classify_candidate_coverage_scope(
                is_election_news=False,
                relevance=relevance,
                development=development,
            ),
            "general",
        )

    def test_incidental_summary_campaign_vocabulary_is_rejected(self):
        cases = [
            (
                "Après l'affaire Barbara Butch, le chef grenoblois de LFI "
                "saisit la justice",
                "Il dénonce une campagne de cyberharcèlement contre lui.",
                [],
            ),
            (
                "Propos de Raphaël Glucksmann sur le Canon français : "
                "qu’a dit le leader de Place publique ?",
                "Raphaël Glucksmann tente de se défaire d'une image, "
                "forgée par LFI, d'un candidat de droite.",
                ["Raphaël Glucksmann"],
            ),
            (
                "Détention provisoire des mineurs: Gérald Darmanin "
                "tente de colmater la brèche",
                "Après avoir renoncé à la mesure phare de son projet de "
                "loi, Gérald Darmanin répond aux députés.",
                ["Gérald Darmanin"],
            ),
            (
                "Hommage de La France insoumise à Robespierre",
                "En 2024, La France insoumise tenait un meeting pour les "
                "élections européennes avec Raphaël Glucksmann.",
                ["Raphaël Glucksmann"],
            ),
            (
                "Raphaël Glucksmann commente la semaine politique",
                "Le Parti socialiste organise une primaire sans rapport.",
                ["Raphaël Glucksmann"],
            ),
            (
                "La France insoumise publie un hommage historique",
                "La France insoumise publie un hommage historique LCP.",
                [],
            ),
        ]

        for headline, summary, candidates in cases:
            matches = match_news_candidates(headline, summary, candidates)
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_relevant_news(
                        headline,
                        summary,
                        candidates,
                        matches,
                    )
                )

    def test_summary_campaign_evidence_is_local_and_minimal(self):
        result = classify_relevant_news(
            "Le Parti socialiste précise son calendrier interne",
            (
                "Le Parti socialiste organise une primaire pour choisir "
                "son candidat. La France insoumise tient ensuite un "
                "meeting culturel sans rapport."
            ),
            [],
            [],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "campaign_or_selection_context")
        self.assertIn("parti socialiste", result["matched_terms"])
        self.assertIn("primaire", result["matched_terms"])
        self.assertNotIn("la france insoumise", result["matched_terms"])
        self.assertNotIn("meeting", result["matched_terms"])

    def test_structured_summary_selection_controls_remain_relevant(self):
        controls = [
            (
                "Le Parti socialiste précise son calendrier interne",
                "Le Parti socialiste organise une primaire pour son candidat.",
                [],
            ),
            (
                "Les Républicains précisent leur calendrier interne",
                "Les Républicains accordent leur investiture à leur candidat.",
                [],
            ),
            (
                "Le Parti socialiste précise son calendrier interne",
                "Le Parti socialiste organise un vote des adhérents pour "
                "la désignation de son candidat.",
                [],
            ),
        ]

        for headline, summary, candidates in controls:
            with self.subTest(summary=summary):
                self.assertIsNotNone(
                    classify_relevant_news(
                        headline,
                        summary,
                        candidates,
                        match_news_candidates(headline, summary, candidates),
                    )
                )

    def test_current_candidacy_summary_controls_remain_relevant(self):
        controls = [
            (
                "Raphaël Glucksmann à la ferme : les animaux de Daniel",
                "Notre chroniqueur imagine les vacances de l'eurodéputé "
                "de Place publique et aspirant candidat à l'Elysée en 2027.",
                ["Raphaël Glucksmann"],
            ),
            (
                "Jérôme Karsenti : Marine Le Pen a bafoué les principes "
                "démocratiques",
                "La candidature de la cheffe de file du RN à la présidentielle "
                "s'inscrit dans une époque de banalisation de la corruption.",
                ["Marine Le Pen"],
            ),
            (
                "Raphaël Glucksmann précise son calendrier",
                "Sa candidature à l'élection présidentielle de 2027 sera "
                "discutée cet été.",
                ["Raphaël Glucksmann"],
            ),
        ]

        for headline, summary, candidates in controls:
            matches = match_news_candidates(headline, summary, candidates)
            with self.subTest(headline=headline):
                self.assertIsNotNone(
                    classify_relevant_news(
                        headline,
                        summary,
                        candidates,
                        matches,
                    )
                )

    def test_long_and_short_presidential_controls_remain_relevant(self):
        long_summary = (
            ("Contexte politique sans signal électoral. " * 45)
            + "Le Parti socialiste prépare son candidat à l'élection "
            + "présidentielle de 2027."
        )
        long_result = classify_relevant_news(
            "Le Parti socialiste précise son calendrier",
            long_summary,
            [],
            [],
        )
        google_result = classify_relevant_news(
            "Présidentielle 2027 : le parti prépare sa primaire",
            "Présidentielle 2027 : le parti prépare sa primaire Le Monde",
            [],
            [],
        )

        self.assertIsNotNone(long_result)
        self.assertEqual(
            long_result["reason"],
            "summary_confirmed_presidential_context",
        )
        self.assertIsNotNone(google_result)
        self.assertEqual(google_result["reason"], "presidential_context")

    def test_current_election_signals_reject_historical_presidential_years(self):
        self.assertEqual(
            current_presidential_matches(
                normalize("Présidentielle 2012: la victoire du président normal")
            ),
            [],
        )
        self.assertTrue(
            current_presidential_matches(
                normalize("Présidentielle 2027: une alliance est proposée")
            )
        )

    def test_static_candidate_directory_pages_are_not_articles(self):
        self.assertTrue(
            is_static_entity_page(
                "Jean-Luc Mélenchon",
                "https://www.bfmtv.com/politique/jean-luc-melenchon_DN-201701010040.html",
                ["Jean-Luc Mélenchon"],
            )
        )
        self.assertTrue(
            is_static_entity_page(
                "Sébastien Lecornu Premier ministre",
                "https://www.bfmtv.com/politique/sebastien-lecornu-premier-ministre_DN-202509100375.html",
                ["Sébastien Lecornu"],
            )
        )
        self.assertFalse(
            is_static_entity_page(
                "Présidentielle 2027: Jean-Luc Mélenchon propose un accord aux Écologistes",
                "https://www.bfmtv.com/politique/example_AD-202607220391.html",
                ["Jean-Luc Mélenchon"],
            )
        )

    def test_zero_item_limit_means_unlimited(self):
        items = [{"id": index} for index in range(75)]
        self.assertEqual(limit_items(items, 0), items)
        self.assertEqual(len(limit_items(items, 12)), 12)


    @staticmethod
    def inventory_entry(
        published_at: datetime,
        headline: str = "Presidentielle 2027 : un article",
        summary: str = "Contexte politique.",
    ):
        return {
            "source_id": "example",
            "publisher": "Example",
            "feed_url": "https://example.test/rss",
            "politics_specific": True,
            "headline": headline,
            "summary": summary,
            "url": "https://example.test/article",
            "canonical_url": "https://example.test/article",
            "published_at": published_at,
            "candidate_names": [],
            "candidate_matches": [],
        }

    def test_inventory_retains_article_after_it_leaves_the_feed(self):
        first_run = datetime(2026, 7, 22, 10, tzinfo=timezone.utc)
        entry = self.inventory_entry(first_run - timedelta(days=2))
        relevance = classify_relevant_news(
            normalize(entry["headline"]),
            normalize(entry["summary"]),
            entry["candidate_names"],
            entry["candidate_matches"],
        )
        self.assertIsNotNone(relevance)
        entry["relevance_reason"] = relevance["reason"]
        entry["relevance_terms"] = relevance["matched_terms"]
        first, _entries, stats = merge_inventory(
            {"schema_version": 3, "generated_at": None, "window_days": 30, "items": []},
            [entry],
            first_run,
            30,
        )
        self.assertEqual(stats["new_items_discovered"], 1)

        second, entries, stats = merge_inventory(
            first,
            [],
            first_run + timedelta(hours=1),
            30,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(stats["retained_inventory_items"], 1)
        self.assertEqual(stats["new_items_discovered"], 0)
        self.assertEqual(second, first)

    def test_inventory_prunes_articles_after_the_window(self):
        first_run = datetime(2026, 7, 1, 10, tzinfo=timezone.utc)
        first, _entries, _stats = merge_inventory(
            {"schema_version": 3, "generated_at": None, "window_days": 30, "items": []},
            [self.inventory_entry(first_run)],
            first_run,
            30,
        )

        second, entries, stats = merge_inventory(
            first,
            [],
            first_run + timedelta(days=31),
            30,
        )
        self.assertEqual(entries, [])
        self.assertEqual(second["items"], [])
        self.assertEqual(stats["expired_inventory_items"], 1)

    def test_inventory_does_not_store_full_feed_content(self):
        generated_at = datetime(2026, 7, 22, 10, tzinfo=timezone.utc)
        payload, _entries, _stats = merge_inventory(
            {"schema_version": 3, "generated_at": None, "window_days": 30, "items": []},
            [self.inventory_entry(generated_at, summary="x" * 5000)],
            generated_at,
            30,
        )
        self.assertEqual(len(payload["items"][0]["summary"]), 1000)


    def test_inventory_preserves_candidate_matches_beyond_summary_limit(self):
        generated_at = datetime(2026, 7, 22, 10, tzinfo=timezone.utc)
        entry = self.inventory_entry(
            generated_at,
            headline="Une actualité gouvernementale",
            summary=("x" * 1200) + " Gabriel Attal",
        )
        # build_wire derives this from the complete feed summary before
        # merge_inventory stores only the bounded summary.
        entry["candidate_matches"] = [
            {
                "candidate": "Gabriel Attal",
                "matched_aliases": ["gabriel attal"],
                "locations": ["summary"],
            }
        ]
        entry["candidate_names"] = candidate_names_from_matches(
            entry["candidate_matches"]
        )
        entry["relevance_reason"] = "campaign_or_selection_context"
        entry["relevance_terms"] = ["presidentielle"]

        payload, entries, _stats = merge_inventory(
            {"schema_version": 3, "generated_at": None, "window_days": 30, "items": []},
            [entry],
            generated_at,
            30,
        )

        self.assertEqual(len(payload["items"][0]["summary"]), 1000)
        self.assertEqual(
            payload["items"][0]["candidate_names"],
            ["Gabriel Attal"],
        )
        self.assertEqual(entries[0]["candidate_names"], ["Gabriel Attal"])
        self.assertEqual(
            entries[0]["candidate_matches"],
            entry["candidate_matches"],
        )
        self.assertEqual(
            payload["items"][0]["relevance_reason"],
            "campaign_or_selection_context",
        )
        self.assertEqual(
            entries[0]["relevance_terms"],
            ["presidentielle"],
        )

    def retained_semantic_entry(
        self,
        published_at,
        slug,
        headline,
        summary,
        candidates,
        relevance=None,
        source=None,
    ):
        item = self.inventory_entry(
            published_at,
            headline=headline,
            summary=summary,
        )
        if source is not None:
            item.update(
                {
                    "source_id": source["source_id"],
                    "publisher": source["name"],
                    "feed_url": source["feed_url"],
                }
            )
        item["url"] = f"https://example.test/{slug}"
        item["canonical_url"] = item["url"]
        item["candidate_matches"] = match_news_candidates(
            headline,
            summary,
            candidates,
        )
        item["candidate_names"] = candidate_names_from_matches(
            item["candidate_matches"]
        )
        if relevance is None:
            relevance = classify_relevant_news(
                normalize(headline),
                normalize(summary),
                item["candidate_names"],
                item["candidate_matches"],
            )
            self.assertIsNotNone(relevance)
        item["relevance_reason"] = relevance["reason"]
        item["relevance_terms"] = list(relevance["matched_terms"])
        return item

    def test_current_inventory_reclassifies_relevance_without_provenance_churn(self):
        generated_at = datetime(2026, 7, 28, 8, tzinfo=timezone.utc)
        stale = self.retained_semantic_entry(
            generated_at - timedelta(hours=2),
            "retained-support",
            (
                "David Lisnard est allé au soutien des communes "
                "incendiées dans le Var"
            ),
            "Une visite auprès des sinistrés.",
            ["David Lisnard"],
            {
                "reason": "campaign_or_selection_context",
                "matched_terms": ["soutien"],
            },
        )
        endorsement = self.retained_semantic_entry(
            generated_at - timedelta(hours=2),
            "retained-endorsement",
            (
                "François Hollande annonce son soutien à la candidature "
                "de Raphaël Glucksmann en 2027"
            ),
            "Un choix annoncé publiquement.",
            ["François Hollande", "Raphaël Glucksmann"],
        )
        summary_confirmed = self.retained_semantic_entry(
            generated_at - timedelta(hours=2),
            "retained-summary-context",
            "Le Parti socialiste précise son calendrier interne",
            (
                "La primaire doit désigner son candidat à l'élection "
                "présidentielle de 2027."
            ),
            [],
        )
        previous, _entries, _stats = merge_inventory(
            {
                "schema_version": INVENTORY_SCHEMA_VERSION,
                "generated_at": None,
                "window_days": 30,
                "items": [],
            },
            [stale, endorsement, summary_confirmed],
            generated_at,
            30,
        )
        before = {
            item["canonical_url"]: copy.deepcopy(item)
            for item in previous["items"]
        }
        refreshed, entries, stats = merge_inventory(
            previous,
            [],
            generated_at + timedelta(hours=1),
            30,
        )
        after = {item["canonical_url"]: item for item in refreshed["items"]}
        stale_item = after[stale["canonical_url"]]

        self.assertEqual(stats["retained_inventory_items"], 3)
        self.assertEqual(
            {item["id"] for item in refreshed["items"]},
            {item["id"] for item in previous["items"]},
        )
        self.assertIsNone(stale_item["relevance_reason"])
        self.assertEqual(stale_item["relevance_terms"], [])
        for field, value in before[stale["canonical_url"]].items():
            if field not in {"relevance_reason", "relevance_terms"}:
                self.assertEqual(stale_item[field], value, field)
        self.assertEqual(
            after[endorsement["canonical_url"]]["relevance_reason"],
            "campaign_or_selection_context",
        )
        self.assertIn(
            "electoral_support",
            after[endorsement["canonical_url"]]["relevance_terms"],
        )
        self.assertEqual(
            after[summary_confirmed["canonical_url"]]["relevance_reason"],
            "summary_confirmed_presidential_context",
        )
        self.assertEqual(len(entries), 3)

        second, second_entries, second_stats = merge_inventory(
            refreshed,
            [],
            generated_at + timedelta(hours=2),
            30,
        )
        self.assertEqual(second, refreshed)
        self.assertEqual(second_entries, entries)
        self.assertEqual(second_stats["refreshed_inventory_items"], 0)
        self.assertEqual(
            [
                (item["id"], item["first_seen_at"], item["last_seen_at"])
                for item in second["items"]
            ],
            [
                (item["id"], item["first_seen_at"], item["last_seen_at"])
                for item in refreshed["items"]
            ],
        )

    def test_build_wire_refreshes_retained_semantics_and_keeps_full_input_override(self):
        generated_at = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
        source = {
            "source_id": "retained-test-source",
            "name": "Retained Test Source",
            "feed_url": "https://example.test/rss",
            "politics_specific": True,
        }
        sources = [
            {
                **source,
                "source_id": f"retained-test-source-{index}",
                "feed_url": f"https://example.test/rss-{index}",
            }
            for index in range(4)
        ]
        source = sources[0]
        stale_headline = (
            "David Lisnard est allé au soutien des communes incendiées "
            "dans le Var"
        )
        stale_summary = "Une visite auprès des sinistrés."
        stale = self.retained_semantic_entry(
            generated_at - timedelta(hours=3),
            "stale-support",
            stale_headline,
            stale_summary,
            ["David Lisnard"],
            {
                "reason": "campaign_or_selection_context",
                "matched_terms": ["soutien"],
            },
            source,
        )
        self.assertIsNone(
            classify_relevant_news(
                normalize(stale_headline),
                normalize(stale_summary),
                stale["candidate_names"],
                stale["candidate_matches"],
            )
        )
        endorsement = self.retained_semantic_entry(
            generated_at - timedelta(hours=3),
            "genuine-endorsement",
            (
                "François Hollande annonce son soutien à la candidature "
                "de Raphaël Glucksmann en 2027"
            ),
            "Un choix annoncé publiquement.",
            ["François Hollande", "Raphaël Glucksmann"],
            source=source,
        )
        summary_control = self.retained_semantic_entry(
            generated_at - timedelta(hours=3),
            "summary-confirmed",
            "Le Parti socialiste confirme son calendrier",
            (
                "La primaire doit désigner son candidat à l'élection "
                "présidentielle de 2027."
            ),
            [],
            source=source,
        )
        override_headline = "Le Parti socialiste publie son calendrier"
        compact_summary = "x" * 1000
        full_summary = (
            ("x" * 1200)
            + " La primaire doit désigner son candidat à l'élection "
            + "présidentielle de 2027."
        )
        override_relevance = classify_relevant_news(
            normalize(override_headline),
            normalize(full_summary),
            [],
            [],
        )
        self.assertIsNotNone(override_relevance)
        self.assertIsNone(
            classify_relevant_news(
                normalize(override_headline),
                normalize(compact_summary),
                [],
                [],
            )
        )
        override = self.retained_semantic_entry(
            generated_at - timedelta(hours=3),
            "full-input-override",
            override_headline,
            compact_summary,
            [],
            override_relevance,
            source,
        )
        previous, _entries, _stats = merge_inventory(
            {
                "schema_version": INVENTORY_SCHEMA_VERSION,
                "generated_at": None,
                "window_days": 30,
                "items": [],
            },
            [stale, endorsement, summary_control, override],
            generated_at - timedelta(hours=1),
            30,
        )
        previous_ids = {item["id"] for item in previous["items"]}
        current_feed = f"""<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel><item>
          <title>{override_headline}</title>
          <link>{override['url']}</link>
          <pubDate>{format_datetime(generated_at - timedelta(hours=2))}</pubDate>
          <description>{full_summary}</description>
        </item></channel></rss>""".encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            polls_path = Path(directory) / "polls.json"
            polls_path.write_text(
                json.dumps(
                    {
                        "events": [{
                            "round": "first_round",
                            "fieldwork_end": "2026-07-28",
                            "candidates": [
                                {"name": "David Lisnard"},
                                {"name": "François Hollande"},
                                {"name": "Raphaël Glucksmann"},
                            ],
                        }]
                    }
                ),
                encoding="utf-8",
            )
            inventory_path = Path(directory) / "inventory.json"
            inventory_path.write_text(json.dumps(previous), encoding="utf-8")
            with (
                patch("fetch_news_wire.SOURCES", sources),
                patch(
                    "fetch_news_wire.PUBLISHER_POLICY",
                    {
                        "example.test": {
                            "name": source["name"],
                            "source_type": "media",
                            "enabled": True,
                        }
                    },
                ),
                patch(
                    "fetch_news_wire.generate_discovery_queries",
                    return_value=[{
                        "id": "retained-test-discovery",
                        "label": "Retained test discovery",
                        "query": "presidentielle 2027",
                        "kind": "static",
                        "feed_url": (
                            "https://news.google.com/rss/search?"
                            "q=presidentielle+2027"
                        ),
                    }],
                ),
                patch(
                    "fetch_news_wire.generate_publisher_site_feeds",
                    return_value=[{
                        "id": "publisher-site:example.test",
                        "label": "Retained test publisher site",
                        "publisher": source["name"],
                        "domain": "example.test",
                        "tier": "core",
                        "query": "site:example.test presidentielle 2027",
                        "feed_url": (
                            "https://news.google.com/rss/search?"
                            "q=site%3Aexample.test+presidentielle+2027"
                        ),
                        "interval_hours": 1,
                        "slot": 0,
                    }],
                ),
                patch(
                    "fetch_news_wire.fetch_news_route",
                    side_effect=lambda url, **_kwargs: successful_fetch(
                        current_feed, url
                    ),
                ),
            ):
                payload, inventory = build_wire(
                    polls_path,
                    30,
                    0,
                    inventory_path,
                    generated_at=generated_at,
                )

        inventory_by_url = {
            item["canonical_url"]: item for item in inventory["items"]
        }
        self.assertEqual(
            {item["id"] for item in inventory["items"]}, previous_ids
        )
        stale_inventory = inventory_by_url[stale["canonical_url"]]
        self.assertIsNone(stale_inventory["relevance_reason"])
        self.assertEqual(stale_inventory["relevance_terms"], [])
        self.assertEqual(
            stale_inventory["candidate_matches"], stale["candidate_matches"]
        )
        relevant_ids = {item["id"] for item in payload["relevant_news"]}
        watch_by_id = {
            item["id"]: item for item in payload["candidate_watch"]
        }
        self.assertNotIn(stale_inventory["id"], relevant_ids)
        self.assertEqual(
            watch_by_id[stale_inventory["id"]]["coverage_scope"], "general"
        )
        self.assertNotIn(
            stale_inventory["id"],
            {item["id"] for item in payload["election_news"]},
        )
        self.assertNotIn(
            stale_inventory["id"],
            {item["id"] for item in payload["notable_developments"]},
        )
        endorsement_inventory = inventory_by_url[endorsement["canonical_url"]]
        self.assertIn(endorsement_inventory["id"], relevant_ids)
        self.assertEqual(
            watch_by_id[endorsement_inventory["id"]]["coverage_scope"],
            "campaign",
        )
        self.assertIn(
            inventory_by_url[summary_control["canonical_url"]]["id"],
            relevant_ids,
        )
        override_inventory = inventory_by_url[override["canonical_url"]]
        self.assertEqual(len(override_inventory["summary"]), 1000)
        self.assertIsNone(
            classify_relevant_news(
                normalize(override_inventory["headline"]),
                normalize(override_inventory["summary"]),
                override_inventory["candidate_names"],
                override_inventory["candidate_matches"],
            )
        )
        self.assertEqual(
            override_inventory["relevance_reason"],
            "summary_confirmed_presidential_context",
        )
        self.assertIn(override_inventory["id"], relevant_ids)

    def test_fresh_lcp_entry_stays_inventory_and_general_candidate_watch(self):
        generated_at = datetime(2026, 7, 29, 4, tzinfo=timezone.utc)
        headline = (
            "Hommage de La France insoumise à Robespierre: "
            "pourquoi ça fait débat"
        )
        summary = lcp_retrospective_summary()
        article_url = "https://lcp.example/actualites/robespierre"
        feed = f"""<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel><item>
          <title>{headline}</title>
          <link>{article_url}</link>
          <pubDate>{format_datetime(generated_at - timedelta(hours=2))}</pubDate>
          <description>{summary}</description>
        </item></channel></rss>""".encode("utf-8")
        sources = [
            {
                "source_id": f"lcp-regression-{index}",
                "name": "LCP — Actualités",
                "feed_url": f"https://lcp.example/rss-{index}.xml",
                "politics_specific": True,
            }
            for index in range(4)
        ]

        direct_feed_urls = {source["feed_url"] for source in sources}
        empty_feed = b"""<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel></channel></rss>"""
        discovery_queries = [{
            "id": "lcp-regression-discovery",
            "label": "LCP regression discovery",
            "query": "presidentielle 2027",
            "kind": "static",
            "feed_url": (
                "https://news.google.com/rss/search"
                "?q=presidentielle+2027"
            ),
        }]
        publisher_site_feeds = [{
            "id": "publisher-site:lcp.example",
            "label": "LCP publisher-site discovery",
            "publisher": "LCP — Actualités",
            "domain": "lcp.example",
            "tier": "core",
            "query": "site:lcp.example presidentielle 2027",
            "feed_url": "https://news.google.com/rss/search?q=lcp",
            "interval_hours": 1,
            "slot": 0,
        }]

        with tempfile.TemporaryDirectory() as directory:
            polls_path = Path(directory) / "polls.json"
            polls_path.write_text(
                json.dumps(
                    {
                        "events": [{
                            "round": "first_round",
                            "fieldwork_end": "2026-07-29",
                            "candidates": [
                                {"name": "Jean-Luc Mélenchon"},
                                {"name": "Raphaël Glucksmann"},
                            ],
                        }]
                    }
                ),
                encoding="utf-8",
            )
            inventory_path = Path(directory) / "inventory.json"
            with (
                patch("fetch_news_wire.SOURCES", sources),
                patch(
                    "fetch_news_wire.generate_discovery_queries",
                    return_value=discovery_queries,
                ),
                patch(
                    "fetch_news_wire.generate_publisher_site_feeds",
                    return_value=publisher_site_feeds,
                ),
                patch(
                    "fetch_news_wire.PUBLISHER_POLICY",
                    {"lcp.example": {
                        "name": "LCP — Actualités",
                        "source_type": "media",
                        "enabled": True,
                    }},
                ),
                patch(
                    "fetch_news_wire.fetch_news_route",
                    side_effect=lambda url, **_kwargs: successful_fetch(
                        feed if url in direct_feed_urls else empty_feed,
                        url,
                    ),
                ),
            ):
                payload, inventory = build_wire(
                    polls_path,
                    30,
                    0,
                    inventory_path,
                    generated_at=generated_at,
                )

        self.assertEqual(len(inventory["items"]), 1)
        inventory_item = inventory["items"][0]
        item_id = inventory_item["id"]
        self.assertEqual(len(inventory_item["summary"]), 1000)
        self.assertEqual(
            inventory_item["candidate_names"],
            ["Jean-Luc Mélenchon", "Raphaël Glucksmann"],
        )
        self.assertEqual(
            inventory_item["candidate_matches"],
            [
                {
                    "candidate": "Jean-Luc Mélenchon",
                    "matched_aliases": ["jean luc melenchon"],
                    "locations": ["summary"],
                },
                {
                    "candidate": "Raphaël Glucksmann",
                    "matched_aliases": ["raphael glucksmann"],
                    "locations": ["summary"],
                },
            ],
        )
        self.assertIsNone(inventory_item["relevance_reason"])
        self.assertNotIn(
            item_id,
            {item["id"] for item in payload["relevant_news"]},
        )
        self.assertNotIn(
            item_id,
            {item["id"] for item in payload["election_news"]},
        )
        self.assertNotIn(
            item_id,
            {item["id"] for item in payload["notable_developments"]},
        )
        watch_by_id = {
            item["id"]: item for item in payload["candidate_watch"]
        }
        self.assertEqual(watch_by_id[item_id]["coverage_scope"], "general")
        agenda_item_ids = {
            item["id"]
            for topic in payload["campaign_agenda"]["topics"]
            for item in topic["supporting_items"]
        }
        self.assertNotIn(item_id, agenda_item_ids)

    def test_old_inventory_migration_recomputes_strict_candidate_matches(self):
        legacy_item = {
            "id": "stable-inventory-id",
            "source_id": "example",
            "publisher": "Example",
            "feed_url": "https://example.test/rss",
            "politics_specific": True,
            "headline": "Philippe Étienne revient sur sa carrière diplomatique",
            "summary": "Un entretien politique.",
            "url": "https://example.test/philippe-etienne",
            "canonical_url": "https://example.test/philippe-etienne",
            "published_at": "2026-07-22T08:00:00Z",
            "first_seen_at": "2026-07-22T09:00:00Z",
            "last_seen_at": "2026-07-23T09:00:00Z",
            "candidate_names": ["Édouard Philippe"],
            "relevance_reason": "candidate_political_coverage",
            "relevance_terms": ["candidate_in_headline"],
        }
        legacy_payload = {
            "schema_version": 3,
            "generated_at": "2026-07-23T09:00:00Z",
            "window_days": 30,
            "items": [legacy_item],
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            path.write_text(json.dumps(legacy_payload), encoding="utf-8")
            migrated = load_inventory(
                path,
                30,
                ["Édouard Philippe"],
            )

        self.assertEqual(migrated["schema_version"], INVENTORY_SCHEMA_VERSION)
        item = migrated["items"][0]
        self.assertEqual(item["candidate_names"], [])
        self.assertEqual(item["candidate_matches"], [])
        self.assertIsNone(item["relevance_reason"])
        self.assertEqual(item["relevance_terms"], [])
        for field in (
            "id",
            "first_seen_at",
            "last_seen_at",
            "url",
            "canonical_url",
            "published_at",
        ):
            self.assertEqual(item[field], legacy_item[field])

    def test_workflow_validates_candidate_match_contract(self):
        workflow = (
            Path(__file__).parent
            / ".github"
            / "workflows"
            / "update-news-wire.yml"
        ).read_text(encoding="utf-8")
        for contract in (
            'candidate_matches = item.get("candidate_matches")',
            'set(match) != approved_candidate_match_keys',
            'approved_candidate_locations = ("headline", "summary")',
            'len(matched_aliases) != len(set(matched_aliases))',
            'sorted(matched_candidates) != sorted(candidates)',
        ):
            self.assertIn(contract, workflow)


    def test_foreign_presidential_races_require_a_french_anchor(self):
        rejected = [
            (
                "Brésil : en difficulté, Flavio Bolsonaro se lance "
                "dans la course présidentielle",
                "",
                [],
            ),
            (
                "Donald Trump relance sa campagne présidentielle",
                "",
                [],
            ),
            (
                "Roumanie : les candidats se préparent à "
                "l'élection présidentielle",
                "",
                [],
            ),
        ]

        for headline, summary, candidates in rejected:
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_relevant_news(
                        normalize(headline),
                        normalize(summary),
                        candidates,
                    )
                )

        accepted = [
            (
                "Présidentielle 2027 : Jean-Luc Mélenchon "
                "propose un accord aux Écologistes",
                "",
                ["Jean-Luc Mélenchon"],
            ),
            (
                "Marine Le Pen prépare sa candidature à l'Élysée",
                "",
                ["Marine Le Pen"],
            ),
            (
                "Ce que la victoire de Trump pourrait changer "
                "pour la présidentielle française de 2027",
                "",
                [],
            ),
            (
                "Le Parti socialiste prépare la présidentielle",
                "",
                [],
            ),
        ]

        for headline, summary, candidates in accepted:
            with self.subTest(headline=headline):
                self.assertIsNotNone(
                    classify_relevant_news(
                        normalize(headline),
                        normalize(summary),
                        candidates,
                    )
                )


    def test_retained_foreign_presidential_provenance_is_revalidated(self):
        generated_at = datetime(
            2026,
            7,
            25,
            16,
            tzinfo=timezone.utc,
        )
        source = SOURCES[0]

        retained_entry = self.inventory_entry(
            generated_at - timedelta(hours=2),
            headline=(
                "Présidentielle 2027 : une alliance est annoncée"
            ),
        )
        retained_entry.update(
            {
                "source_id": source["source_id"],
                "publisher": source["name"],
                "feed_url": source["feed_url"],
                "politics_specific": bool(
                    source.get("politics_specific")
                ),
                "url": "https://example.test/french-alliance",
                "canonical_url": (
                    "https://example.test/french-alliance"
                ),
            }
        )

        foreign_entry = self.inventory_entry(
            generated_at - timedelta(hours=3),
            headline=(
                "Brésil : en difficulté, Flavio Bolsonaro "
                "se lance dans la course présidentielle"
            ),
        )
        foreign_entry.update(
            {
                "source_id": source["source_id"],
                "publisher": source["name"],
                "feed_url": source["feed_url"],
                "politics_specific": bool(
                    source.get("politics_specific")
                ),
                "url": "https://example.test/bolsonaro",
                "canonical_url": "https://example.test/bolsonaro",
                # Simulate provenance stored by the previous rules.
                "relevance_reason": "presidential_context",
                "relevance_terms": ["presidentielle"],
            }
        )

        previous_inventory, _entries, _stats = merge_inventory(
            {
                "schema_version": 3,
                "generated_at": None,
                "window_days": 30,
                "items": [],
            },
            [
                retained_entry,
                foreign_entry,
            ],
            generated_at - timedelta(hours=1),
            30,
        )

        def fake_fetch(url, **_kwargs):
            return not_modified_fetch(url)

        with tempfile.TemporaryDirectory() as directory:
            inventory_path = Path(directory) / "inventory.json"
            inventory_path.write_text(
                json.dumps(previous_inventory),
                encoding="utf-8",
            )

            with (
                patch(
                    "fetch_news_wire.fetch_news_route",
                    side_effect=fake_fetch,
                ),
                patch(
                    "fetch_news_wire.parse_feed",
                    side_effect=AssertionError(
                        "304 response must not be parsed"
                    ),
                ),
            ):
                payload, inventory = build_wire(
                    Path("polls.json"),
                    30,
                    0,
                    inventory_path,
                    generated_at=generated_at,
                )

        foreign_records = [
            item
            for item in inventory["items"]
            if "bolsonaro" in item["headline"].casefold()
        ]

        self.assertEqual(len(foreign_records), 1)
        self.assertIsNone(
            foreign_records[0]["relevance_reason"]
        )
        self.assertEqual(
            foreign_records[0]["relevance_terms"],
            [],
        )

        public_projection = {
            "election_news": payload["election_news"],
            "notable_developments": payload[
                "notable_developments"
            ],
            "relevant_news": payload["relevant_news"],
            "candidate_watch": payload["candidate_watch"],
            "campaign_agenda": payload["campaign_agenda"],
        }

        public_text = json.dumps(
            public_projection,
            ensure_ascii=False,
        ).casefold()

        self.assertNotIn(
            foreign_records[0]["id"].casefold(),
            public_text,
        )
        self.assertNotIn(
            "flavio bolsonaro",
            public_text,
        )
        self.assertNotIn(
            "https://example.test/bolsonaro",
            public_text,
        )
        self.assertEqual(len(payload["relevant_news"]), 1)

class CandidateVisibilityComparisonTests(unittest.TestCase):
    generated_at = datetime(2026, 7, 26, 20, 35, tzinfo=timezone.utc)

    @staticmethod
    def records(
        count,
        publishers,
        published_at,
        prefix,
    ):
        return [
            {
                "id": f"{prefix}-{index}",
                "publisher": publishers[index % len(publishers)],
                "published_at": published_at,
                "coverage_scope": "campaign",
            }
            for index in range(count)
        ]

    def visibility(
        self,
        current_count,
        prior_count,
        current_publishers,
        prior_publishers,
    ):
        records = self.records(
            current_count,
            current_publishers,
            "2026-07-26T12:00:00Z",
            "current",
        ) + self.records(
            prior_count,
            prior_publishers,
            "2026-07-19T12:00:00Z",
            "prior",
        )
        return (
            build_candidate_visibility(records, self.generated_at),
            records,
        )

    def test_exact_adjacent_seven_day_boundaries(self):
        records = [
            *self.records(1, ["Current start"], "2026-07-20T00:00:00Z", "cs"),
            *self.records(1, ["Current end"], "2026-07-26T23:59:59Z", "ce"),
            *self.records(1, ["Prior start"], "2026-07-13T00:00:00Z", "ps"),
            *self.records(1, ["Prior end"], "2026-07-19T23:59:59Z", "pe"),
            *self.records(1, ["Outside old"], "2026-07-12T23:59:59Z", "old"),
            *self.records(1, ["Outside new"], "2026-07-27T00:00:00Z", "new"),
        ]
        visibility = build_candidate_visibility(records, self.generated_at)

        self.assertEqual(
            visibility["current_period"],
            {
                "start_date": "2026-07-20",
                "end_date": "2026-07-26",
                "record_count": 2,
                "publisher_count": 2,
                "publisher_names": ["Current end", "Current start"],
                "candidate_metrics": [],
            },
        )
        self.assertEqual(
            visibility["prior_period"],
            {
                "start_date": "2026-07-13",
                "end_date": "2026-07-19",
                "record_count": 2,
                "publisher_count": 2,
                "publisher_names": ["Prior end", "Prior start"],
                "candidate_metrics": [],
            },
        )

    def test_audited_publisher_panel_failure(self):
        current = [f"Current {index:02d}" for index in range(55)]
        prior = current[:5] + [f"Prior {index:02d}" for index in range(3)]
        visibility, _records = self.visibility(173, 29, current, prior)
        quality = visibility["comparison_quality"]

        self.assertEqual(quality["status"], "not_comparable")
        self.assertEqual(quality["reason"], "publisher_panel_changed")
        self.assertEqual(quality["publisher_overlap_ratio"], 0.086)
        self.assertEqual(quality["record_count_ratio"], 5.966)

    def test_insufficient_period_records(self):
        publishers = [f"Publisher {index}" for index in range(5)]
        visibility, _records = self.visibility(9, 10, publishers, publishers)
        self.assertEqual(
            visibility["comparison_quality"]["reason"],
            "insufficient_data",
        )

    def test_insufficient_period_publishers(self):
        current = [f"Publisher {index}" for index in range(4)]
        prior = [*current, "Publisher 4"]
        visibility, _records = self.visibility(10, 10, current, prior)
        self.assertEqual(
            visibility["comparison_quality"]["reason"],
            "insufficient_data",
        )

    def test_insufficient_common_publishers(self):
        current = [f"Publisher {index}" for index in range(5)]
        prior = current[:4] + ["Prior only"]
        visibility, _records = self.visibility(10, 10, current, prior)
        quality = visibility["comparison_quality"]
        self.assertEqual(quality["common_publisher_count"], 4)
        self.assertEqual(quality["reason"], "insufficient_data")

    def test_comparable_periods(self):
        publishers = [f"Publisher {index}" for index in range(5)]
        visibility, records = self.visibility(10, 10, publishers, publishers)
        quality = visibility["comparison_quality"]
        self.assertEqual(quality["status"], "comparable")
        self.assertEqual(quality["reason"], "comparable")
        validate_candidate_visibility(
            visibility,
            records,
            self.generated_at,
        )

    def test_comparable_at_locked_boundaries(self):
        current = [f"Common {index}" for index in range(5)]
        prior = current + [f"Prior only {index}" for index in range(5)]
        visibility, _records = self.visibility(10, 20, current, prior)
        quality = visibility["comparison_quality"]
        self.assertEqual(quality["current_record_count"], 10)
        self.assertEqual(quality["common_publisher_count"], 5)
        self.assertEqual(quality["current_publisher_count"], 5)
        self.assertEqual(quality["publisher_overlap_ratio"], 0.5)
        self.assertEqual(quality["record_count_ratio"], 2.0)
        self.assertEqual(quality["status"], "comparable")

    def test_zero_record_ratio_is_null_and_insufficient(self):
        publishers = [f"Publisher {index}" for index in range(5)]
        visibility, _records = self.visibility(10, 0, publishers, publishers)
        quality = visibility["comparison_quality"]
        self.assertIsNone(quality["record_count_ratio"])
        self.assertEqual(quality["status"], "not_comparable")
        self.assertEqual(quality["reason"], "insufficient_data")

    def test_schema_and_thresholds_are_exact(self):
        publishers = [f"Publisher {index}" for index in range(5)]
        visibility, _records = self.visibility(10, 10, publishers, publishers)
        self.assertEqual(
            set(visibility),
            {
                "method",
                "primary_scopes",
                "secondary_scope",
                "current_period",
                "prior_period",
                "general_current_period",
                "general_prior_period",
                "comparison_quality",
            },
        )
        self.assertEqual(
            visibility["method"],
            CANDIDATE_VISIBILITY_METHOD,
        )
        self.assertEqual(
            visibility["primary_scopes"],
            ["election", "campaign"],
        )
        self.assertEqual(
            visibility["secondary_scope"],
            "general",
        )
        self.assertEqual(
            visibility["general_current_period"][
                "record_count"
            ],
            0,
        )
        self.assertEqual(
            visibility["general_prior_period"][
                "record_count"
            ],
            0,
        )
        self.assertEqual(
            visibility["comparison_quality"]["thresholds"],
            CANDIDATE_VISIBILITY_THRESHOLDS,
        )

    def test_validation_rejects_inconsistent_public_contract(self):
        publishers = [f"Publisher {index}" for index in range(5)]
        visibility, records = self.visibility(10, 10, publishers, publishers)
        mutations = {
            "counts": lambda value: value["current_period"].update(
                record_count=11
            ),
            "ratios": lambda value: value["comparison_quality"].update(
                record_count_ratio=1.5
            ),
            "status": lambda value: value["comparison_quality"].update(
                status="not_comparable"
            ),
            "dates": lambda value: value["current_period"].update(
                start_date="2026-07-19"
            ),
            "publisher arrays": lambda value: value["current_period"].update(
                publisher_names=list(reversed(
                    value["current_period"]["publisher_names"]
                ))
            ),
            "threshold types": lambda value: value[
                "comparison_quality"
            ]["thresholds"].update(minimum_period_records=True),
        }

        for label, mutate in mutations.items():
            with self.subTest(label=label):
                invalid = copy.deepcopy(visibility)
                mutate(invalid)
                with self.assertRaises(RuntimeError):
                    validate_candidate_visibility(
                        invalid,
                        records,
                        self.generated_at,
                    )

    def test_workflow_validation_includes_candidate_visibility(self):
        workflow = Path(
            ".github/workflows/update-news-wire.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("validate_output(wire)", workflow)
        self.assertIn("candidate_visibility", workflow)


if __name__ == "__main__":
    unittest.main()
