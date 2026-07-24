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
    DISCOVERY_QUERIES,
    DIRECT_ENTRY_LIMIT,
    DISCOVERY_ENTRY_LIMIT,
    FETCH_WORKERS,
    GOOGLE_NEWS_WORKERS,
    PUBLISHER_POLICY,
    PUBLISHER_SITE_ENTRY_LIMIT,
    SOURCES,
    accept_discovery_entries,
    aggregate_discovered_publishers,
    build_wire,
    build_google_news_url,
    classify_notable_development,
    classify_relevant_news,
    count_contributing_media_publishers,
    current_presidential_matches,
    deduplicate_entries,
    entry_transport,
    explicit_election_match,
    generate_discovery_queries,
    generate_publisher_site_feeds,
    is_static_entity_page,
    limit_items,
    merge_inventory,
    normalize,
    normalize_domain,
    parse_feed,
    publisher_policy_match,
    publisher_site_feed_due,
    remove_publisher_suffix,
    stable_slot,
    transport_priority,
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


class NewsWireRelevanceTests(unittest.TestCase):
    def test_feed_entry_and_concurrency_limits(self):
        self.assertEqual(DIRECT_ENTRY_LIMIT, 20)
        self.assertEqual(DISCOVERY_ENTRY_LIMIT, 10)
        self.assertEqual(PUBLISHER_SITE_ENTRY_LIMIT, 5)
        self.assertLessEqual(FETCH_WORKERS, 12)
        self.assertEqual(GOOGLE_NEWS_WORKERS, 4)

    def test_registry_declares_source_specificity(self):
        self.assertEqual(len(SOURCES), 19)
        self.assertTrue(all(
            isinstance(source.get("politics_specific"), bool)
            for source in SOURCES
        ))

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
        published = format_datetime(datetime.now(timezone.utc))
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
            inventory_path = Path(directory) / "inventory.json"
            review_path = Path(directory) / "publishers.json"
            health_routes = []
            health_attempts = []
            with patch(
                "fetch_news_wire.fetch_news_route",
                side_effect=fake_request,
            ):
                payload, inventory = build_wire(
                    Path("polls.json"),
                    30,
                    0,
                    inventory_path,
                    review_path,
                    health_route_configurations=health_routes,
                    health_attempts=health_attempts,
                )
                review = json.loads(
                    review_path.read_text(encoding="utf-8")
                )

        self.assertEqual(len(payload["sources"]), 19)
        self.assertEqual(payload["counts"]["successful_sources"], 19)
        self.assertEqual(
            payload["discovery"]["configured_queries"],
            len(DISCOVERY_QUERIES) + 5,
        )
        self.assertEqual(payload["discovery"]["successful_queries"], 10)
        self.assertEqual(
            payload["discovery"]["quarantined_items"],
            sum(
                query["quarantined_items"]
                for query in payload["discovery"]["queries"]
            ),
        )
        coverage = payload["feed_coverage"]
        self.assertEqual(coverage["direct_feeds"], 19)
        self.assertEqual(coverage["shared_discovery_feeds"], 10)
        self.assertEqual(coverage["publisher_site_feeds"], 180)
        self.assertEqual(coverage["configured_feeds"], 209)
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
        self.assertEqual(
            coverage["feeds_due_this_run"],
            29 + coverage["publisher_site_feeds_due"],
        )
        self.assertEqual(
            coverage["feeds_successful_this_run"],
            29 + coverage["publisher_site_feeds_successful"],
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
        reduced["feed_coverage"].update(
            {
                "configured_feeds": 30,
                "publisher_site_feeds": 1,
                "publisher_site_feeds_due": reduced_due,
                "publisher_site_feeds_successful": 0,
                "configured_media_publishers": 1,
                "contributing_publishers_30d": 0,
                "feeds_due_this_run": 29 + reduced_due,
                "feeds_successful_this_run": 29,
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
            normalize("Edouard Philippe echoue a faire annuler le statut de la lanceuse d alerte"),
            ["Edouard Philippe"],
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
                "Vise par une enquete Edouard Philippe echoue a faire annuler "
                "le statut de la lanceuse d alerte",
                ["Édouard Philippe"],
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

    def test_broad_relevance_accepts_candidate_commentary(self):
        result = classify_relevant_news(
            normalize("Marine Le Pen ou le trumpisme à la française"),
            normalize("Un éditorial analyse son positionnement politique."),
            ["Marine Le Pen"],
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "candidate_political_coverage")

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
                "Pour 2027 Melenchon tend la main aux Ecologistes",
                "La proposition concerne la prochaine presidentielle.",
                ["Jean-Luc Mélenchon"],
            ),
            (
                "Le Parti socialiste arrete son calendrier",
                "La primaire doit designer son candidat a l election presidentielle de 2027.",
                [],
            ),
            (
                "Marine Le Pen ou le trumpisme a la francaise",
                "Un editorial analyse son positionnement politique.",
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

    def test_broad_relevance_accepts_campaign_and_party_selection(self):
        accepted = [
            (
                "Entretien avec François Hollande sur sa stratégie pour 2027",
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
        }

    def test_inventory_retains_article_after_it_leaves_the_feed(self):
        first_run = datetime(2026, 7, 22, 10, tzinfo=timezone.utc)
        first, _entries, stats = merge_inventory(
            {"schema_version": 3, "generated_at": None, "window_days": 30, "items": []},
            [self.inventory_entry(first_run - timedelta(days=2))],
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
        entry["candidate_names"] = ["Gabriel Attal"]
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
            payload["items"][0]["relevance_reason"],
            "campaign_or_selection_context",
        )
        self.assertEqual(
            entries[0]["relevance_terms"],
            ["presidentielle"],
        )


if __name__ == "__main__":
    unittest.main()
