import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

from fetch_news_wire import (
    DISCOVERY_QUERIES,
    PUBLISHER_POLICY,
    SOURCES,
    accept_discovery_entries,
    aggregate_discovered_publishers,
    build_wire,
    build_google_news_url,
    classify_notable_development,
    classify_relevant_news,
    current_presidential_matches,
    deduplicate_entries,
    explicit_election_match,
    generate_discovery_queries,
    is_static_entity_page,
    limit_items,
    merge_inventory,
    normalize,
    normalize_domain,
    parse_feed,
    publisher_policy_match,
    remove_publisher_suffix,
    validate_output,
)


class NewsWireRelevanceTests(unittest.TestCase):
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

        for source in SOURCES:
            match = publisher_policy_match(
                normalize_domain(source["feed_url"])
            )
            if match is None:
                continue
            _domain, policy = match
            if policy["source_type"] == "media":
                self.assertEqual(policy["name"], source["name"])

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
        discovery = {
            "source_id": "discovery:test-query",
            "publisher": "BFMTV — Politique",
            "headline": "Présidentielle 2027 : une annonce",
            "url": "https://news.google.com/rss/articles/example",
            "canonical_url": "https://news.google.com/rss/articles/example",
            "published_at": published_at,
        }
        direct = {
            "source_id": "bfmtv-politique",
            "publisher": "BFMTV — Politique",
            "headline": "Présidentielle 2027 : une annonce",
            "url": "https://www.bfmtv.com/politique/example.html",
            "canonical_url": "https://bfmtv.com/politique/example.html",
            "published_at": published_at,
        }
        first, first_stats = deduplicate_entries([discovery, direct])
        second, second_stats = deduplicate_entries([discovery, direct])
        self.assertEqual(first, second)
        self.assertEqual(first_stats, second_stats)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["source_id"], "bfmtv-politique")
        self.assertEqual(first_stats["direct_precedence_replacements"], 1)

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

        def fake_request(url, timeout=12):
            if url.startswith("https://news.google.com/"):
                return discovery_feed, url
            return direct_feed, url

        with tempfile.TemporaryDirectory() as directory:
            inventory_path = Path(directory) / "inventory.json"
            review_path = Path(directory) / "publishers.json"
            with patch("fetch_news_wire.request_bytes", side_effect=fake_request):
                payload, inventory = build_wire(
                    Path("polls.json"),
                    30,
                    0,
                    inventory_path,
                    review_path,
                )

        self.assertEqual(len(payload["sources"]), 19)
        self.assertEqual(payload["counts"]["successful_sources"], 19)
        self.assertEqual(
            payload["discovery"]["configured_queries"],
            len(DISCOVERY_QUERIES) + 5,
        )
        self.assertEqual(payload["discovery"]["successful_queries"], 10)
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
