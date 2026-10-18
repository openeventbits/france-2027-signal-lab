"""Separate three-provider presentation, independent semantics and bilingual states."""

import copy
import json
import math
from datetime import timedelta
from candidate_history import HistoryError, instant, iso
import candidate_public_signal_trend as trend
import hashlib
import re
import subprocess
import unittest
from pathlib import Path

from lxml import html
import build_candidate_reference as reference

ROOT = Path(__file__).resolve().parent
PROVIDERS = ["polymarket", "youtube", "bluesky"]


class CandidatePublicSignalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = reference.load_sources(ROOT)
        cls.payload = reference.build_projection(cls.sources, ROOT)

    def setUp(self):
        self.data = copy.deepcopy(self.payload)
        # Known UI states are fixtures, not promises about future live prices.
        self.data["polymarket"].update(status="observed", implied_probability=.4585)
        self.data["youtube"].update(status="observed", hidden_subscriber_count=False,
                                   subscriber_count=217000, channel_view_count=123456789)

    def render(self, lang="fr"):
        return reference.render_public_signals(self.data, lang)

    def document(self, lang="fr"):
        return html.fromstring(self.render(lang))

    def card(self, provider, lang="fr"):
        return self.document(lang).xpath(f'.//article[@data-provider="{provider}"]')[0]

    def value(self, provider, lang="fr"):
        return self.card(provider, lang).xpath('.//p[@class="candidate-public-signal-value"]')[0].text_content()

    def bluesky_observed(self):
        self.data["bluesky"].update(status="observed", followers_count=24014,
            handle="candidate.bsky.social", did="did:plc:" + "a" * 24,
            profile_url="https://bsky.app/profile/did:plc:" + "a" * 24)

    def test_french_section_title(self):
        self.assertIn("SIGNAUX PUBLICS", self.render())

    def test_english_section_title(self):
        self.assertIn("PUBLIC SIGNALS", self.render("en"))

    def test_exactly_three_peer_cards_in_order(self):
        for lang in ("fr", "en"):
            self.assertEqual(self.document(lang).xpath('.//article/@data-provider'), PROVIDERS)

    def test_old_standalone_polymarket_removed_and_wikipedia_outside_grid(self):
        for lang in ("fr", "en"):
            rendered = self.render(lang)
            self.assertNotIn('class="candidate-polymarket"', rendered)
            self.assertNotIn('class="candidate-attention-grid"', rendered)
            self.assertEqual(rendered.count('data-provider="polymarket"'), 1)
            self.assertNotIn('data-provider="wikipedia"', rendered)

    def test_polymarket_percentage_retains_stored_probability(self):
        self.assertEqual(self.value("polymarket"), "45,9\u00a0%")
        self.assertEqual(self.value("polymarket", "en"), "45.9%")

    def test_polymarket_unavailable_is_not_zero(self):
        self.data["polymarket"].update(status="unavailable_no_market", implied_probability=None)
        self.assertEqual(self.value("polymarket"), "Indisponible")
        self.assertEqual(self.value("polymarket", "en"), "Unavailable")
        self.assertFalse(self.card("polymarket").xpath('.//a'))

    def test_polymarket_observed_zero_remains_a_real_zero(self):
        self.data["polymarket"]["implied_probability"] = 0
        self.assertEqual(self.value("polymarket", "en"), "0.0%")

    def test_polymarket_limits_are_available(self):
        self.assertIn("ni une intention de vote ni une prévision FR27", self.card("polymarket").text_content())
        self.assertIn("not voting intention and not an FR27 forecast", self.card("polymarket", "en").text_content())

    def test_youtube_subscribers_locale_formatting(self):
        self.data["youtube"]["subscriber_count"] = 1290000
        self.assertEqual(self.value("youtube"), "1\u202f290\u202f000")
        self.assertEqual(self.value("youtube", "en"), "1,290,000")

    def test_youtube_hidden_subscribers(self):
        self.data["youtube"].update(hidden_subscriber_count=True, subscriber_count=None)
        self.assertEqual(self.value("youtube"), "Abonnés masqués")
        self.assertEqual(self.value("youtube", "en"), "Subscribers hidden")

    def test_youtube_unavailable_channel_is_not_account_absence(self):
        self.data["youtube"]["status"] = "unavailable_no_channel"
        self.assertEqual(self.value("youtube"), "Chaîne officielle non établie")
        self.assertEqual(self.value("youtube", "en"), "Official channel not established")
        self.assertFalse(self.card("youtube").xpath('.//a'))

    def test_youtube_complete_recent_window_has_exact_count(self):
        self.data["youtube"].update(recent_window_complete=True, uploads_last_7d=9)
        self.assertIn("9 vidéos publiées sur 7 j", self.card("youtube").text_content())
        self.assertIn("9 uploads in 7d", self.card("youtube", "en").text_content())

    def test_youtube_incomplete_recent_window_never_displays_partial_count(self):
        self.data["youtube"].update(recent_window_complete=False, uploads_last_7d=987654321)
        for lang, phrase in (("fr", "Activité récente partielle"), ("en", "Recent activity incomplete")):
            card = self.card("youtube", lang).text_content()
            self.assertIn(phrase, card)
            self.assertNotIn("987", card)

    def test_youtube_does_not_promote_channel_views(self):
        text = self.card("youtube").text_content()
        self.assertNotIn(reference._public_signal_number(self.data["youtube"]["channel_view_count"], "fr"), text)

    def test_bluesky_followers_locale_formatting(self):
        self.bluesky_observed()
        self.assertEqual(self.value("bluesky"), "24\u202f014")
        self.assertEqual(self.value("bluesky", "en"), "24,014")

    def test_bluesky_handle_is_supporting_and_did_not_visible(self):
        self.bluesky_observed()
        self.assertIn("@candidate.bsky.social", self.card("bluesky").text_content())
        self.assertNotIn("did:plc:", self.card("bluesky").text_content())

    def test_bluesky_unmapped_account(self):
        self.assertEqual(self.value("bluesky"), "Compte officiel non établi")
        self.assertEqual(self.value("bluesky", "en"), "Official account not established")
        self.assertFalse(self.card("bluesky").xpath('.//a'))

    def test_bluesky_opt_out_suppresses_metrics_handle_and_link(self):
        self.bluesky_observed()
        self.data["bluesky"]["status"] = "unavailable_public_web_opt_out"
        self.assertEqual(self.value("bluesky"), "Données publiques non affichées")
        self.assertEqual(self.value("bluesky", "en"), "Public data not displayed")
        self.assertNotIn("@candidate", self.card("bluesky").text_content())
        self.assertFalse(self.card("bluesky").xpath('.//a'))

    def test_missing_mapped_provider_accounts_are_explicit(self):
        self.data["youtube"]["status"] = "unavailable_channel_missing"
        self.data["bluesky"]["status"] = "unavailable_account_missing"
        self.assertEqual(self.value("youtube", "en"), "Channel unavailable")
        self.assertEqual(self.value("bluesky", "en"), "Account unavailable")

    def full_document(self, lang="fr"):
        # Structural/Attention fixtures deliberately have no provider histories.
        # Production history/current-artifact parity is tested separately below.
        return html.fromstring(reference.render_html(self.data, lang=lang, root=ROOT, signal_histories={}))

    def test_wikipedia_structure_and_method_use_a_stable_fixture(self):
        from test_candidate_attention_contract import candidate_payload, CANDIDACY_BY_ID
        row = candidate_payload(CANDIDACY_BY_ID["marine-le-pen"], views=[10] * 90)
        for key in self.data["attention"]:
            if key in row:
                self.data["attention"][key] = row[key]
        self.data["attention"]["evidence_state"] = "observed"
        for lang in ("fr", "en"):
            wiki = self.full_document(lang).get_element_by_id("attention")
            self.assertEqual(wiki.xpath('.//div[@class="candidate-stat-grid is-large"]//strong/text()'),
                             ["70", "280", "10", "10"])
            labels = (["7 derniers jours", "28 derniers jours", "pic sur 7 jours", "pic de période"]
                      if lang == "fr" else ["last 7 days", "last 28 days", "7-day peak", "period peak"])
            self.assertEqual(wiki.xpath('.//div[@class="candidate-stat-grid is-large"]//span/text()'), labels)
            self.assertEqual(len(wiki.xpath('.//article')), 2)
            self.assertEqual(len(wiki.xpath('.//*[@data-chart="attention-history"]/p')), 1)
            self.assertEqual(len(self.data["attention"]["daily_series"]), 90)
            self.assertEqual(len(wiki.xpath('.//button[@aria-describedby]')), 3)
            self.assertIn("soutien" if lang == "fr" else "support", wiki.text_content())
            self.assertEqual(wiki.get_element_by_id("attention-summary-note").text_content(),
                "Les pages vues Wikipédia mesurent la consultation de l’article. Elles ne mesurent ni soutien, ni sentiment, ni approbation, ni intention de vote."
                if lang == "fr" else "Wikipedia pageviews measure visits to the article. They do not measure support, sentiment, approval or voting intention.")
            self.assertEqual(wiki.get_element_by_id("attention-history-note").text_content(),
                "Pages vues quotidiennes de l’article Wikipédia en français. Des visites répétées peuvent être incluses."
                if lang == "fr" else "Daily pageviews of the French-language Wikipedia article. Repeat visits may be included.")
            self.assertIn(self.data["attention"]["wikipedia_article"]["url"], wiki.xpath('.//a/@href'))
            self.assertIn("90", wiki.text_content())

    def test_wikipedia_existing_values_chart_and_methodology_preserved(self):
        self.data = copy.deepcopy(self.payload)
        from candidate_attention_contract import validate_candidate_attention
        validate_candidate_attention(self.sources["candidate_attention"])
        source = next(r for r in self.sources["candidate_attention"]["candidates"]
                      if r["candidate_id"] == self.data["candidate_id"])
        for key, value in self.data["attention"].items():
            self.assertEqual(value, source[key])
        self.assertEqual(self.data["freshness"]["attention_period_end"],
                         self.sources["candidate_attention"]["period"]["end_date"])
        for lang in ("fr", "en"):
            tree = self.full_document(lang)
            wiki = tree.get_element_by_id("attention")
            values = wiki.xpath('.//div[@class="candidate-stat-grid is-large"]//strong/text()')
            self.assertEqual(values, [reference._public_signal_number(self.data["attention"][key], lang) for key in
                ("latest_7_views", "latest_28_views", "latest_7_peak_views", "period_peak_views")])
            self.assertEqual(len(wiki.xpath('.//*[@data-chart="attention-history"]')), 1)
            self.assertTrue(wiki.xpath('.//*[@id="attention-summary-note"]'))
            self.assertTrue(wiki.xpath('.//*[@id="attention-history-note"]'))
            self.assertFalse(wiki.xpath('.//*[@data-provider]'))
            self.assertEqual(tree.xpath('.//nav[contains(@class,"candidate-local-nav")]/a[@href="#attention"]/text()'), ["ATTENTION"])
            sections = tree.xpath('.//main/section/@id')
            self.assertEqual(sections[sections.index("scrutiny"):sections.index("events")+1],
                ["scrutiny", "attention", "public-signals", "events"])

    def test_wikipedia_unavailable_preserves_original_empty_states(self):
        self.data = reference.build_projection(self.sources, ROOT, candidate_id="benoit-mathieu")
        for lang, phrase in (("fr", "Attention Wikipédia indisponible"), ("en", "Wikipedia attention unavailable")):
            tree = self.full_document(lang)
            wiki = tree.get_element_by_id("attention")
            self.assertIn(phrase, wiki.text_content())
            self.assertFalse(wiki.xpath('.//*[@data-chart="attention-history"]'))
            self.assertFalse(wiki.xpath('.//a'))
            self.assertEqual(len(tree.get_element_by_id("public-signals").xpath('.//article[@data-provider]')), 3)

    def test_no_aggregate_or_common_scale_markup(self):
        for lang in ("fr", "en"):
            rendered = self.render(lang)
            self.assertNotRegex(rendered, r'<(?:progress|meter)\b|data-(?:score|rank|momentum)=')
            self.assertNotIn("engagement score", rendered.lower())
            self.assertNotIn("popularity index", rendered.lower())

    def test_independence_and_no_popularity_claim(self):
        self.bluesky_observed()
        self.assertIn("ni un score de popularité ni une intention de vote", self.render())
        self.assertIn("neither a popularity score nor voting intention", self.render("en"))
        self.assertEqual([self.card(provider, "en").xpath('.//p[@class="candidate-public-signal-unit"]')[0].text_content()
                          for provider in PROVIDERS],
                         ["Implied probability", "Subscribers", "Followers"])

    def test_no_runtime_provider_fetch(self):
        source = (ROOT / "assets/candidate-page.js").read_text(encoding="utf-8")
        self.assertNotRegex(source, r'fetch\([^\n]*(?:wikipedia\.org|polymarket\.com|youtube|bsky\.app)')
        self.assertNotIn("<script", self.render())

    def test_provider_source_urls_only_for_observed_accounts(self):
        self.bluesky_observed()
        for provider in PROVIDERS:
            links = self.card(provider).xpath('.//a')
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0].get("target"), "_blank")
            self.assertEqual(links[0].get("rel"), "noopener noreferrer")
            self.assertTrue(links[0].text_content())

    def test_unsafe_or_wrong_provider_source_urls_are_not_links(self):
        for value in ("javascript:alert(1)", "https://evil.test/channel/UC123", "https://www.youtube.com:bad/channel/x"):
            self.data["youtube"]["channel_url"] = value
            self.assertFalse(self.card("youtube").xpath('.//a'))

    def test_bilingual_structural_parity_and_unique_ids(self):
        trees = [self.document(lang) for lang in ("fr", "en")]
        self.assertEqual([node.tag for node in trees[0].iter()], [node.tag for node in trees[1].iter()])
        for tree in trees:
            ids = tree.xpath('.//@id')
            self.assertEqual(len(ids), len(set(ids)))
        for lang in ("fr", "en"):
            ids = self.full_document(lang).xpath(".//@id")
            self.assertEqual(len(ids), len(set(ids)))

    def test_responsive_geometry_keeps_three_readable_columns_without_an_orphan(self):
        css = (ROOT / "assets/candidate-page.css").read_text(encoding="utf-8")
        public_css = css[css.index("/* Public sources reuse candidate panels"):]
        self.assertRegex(public_css, r'candidate-public-signals-grid\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\)')
        self.assertRegex(public_css, r'@media \(min-width: 880px\)\s*\{\s*\.candidate-page \.candidate-public-signals-grid[^}]*repeat\(3, minmax\(0, 1fr\)\)')
        self.assertNotIn("repeat(2,", public_css)
        self.assertIn("overflow-wrap: anywhere", css)

    def test_narrow_desktop_rows_are_scoped_above_the_existing_mobile_boundary(self):
        css = (ROOT / "assets/candidate-page.css").read_text(encoding="utf-8")
        start = css.index('@media (min-width: 760px) and (max-width: 879.98px)')
        rows = css[start:css.index('\n.candidate-page .candidate-public-signal-change {', start)]
        self.assertIn('grid-template-columns: 150px minmax(0, 1fr)', rows)
        self.assertIn('minmax(140px, 1fr) minmax(140px, 1fr) max-content', rows)
        self.assertIn('grid-column: 3', rows)  # Native source link, not a new button.
        self.assertNotRegex(rows, r'font-size|(?:min-)?height:')

    def test_mature_history_support_has_its_own_row_without_chart_overlap(self):
        css = (ROOT / "assets/candidate-page.css").read_text(encoding="utf-8")
        self.assertRegex(css, r':has\(\.candidate-public-signal-change\) \.candidate-public-signal-support\s*\{[^}]*grid-row: 4')
        self.assertRegex(css, r'candidate-public-signal \.candidate-public-signal-trend\s*\{[^}]*grid-row: 2 / span 2')

    def test_three_column_tooltip_placement_keeps_native_visual_styles(self):
        css = (ROOT / "assets/candidate-page.css").read_text(encoding="utf-8")
        public_css = css[css.index("/* Public sources reuse candidate panels"):]
        rules = re.findall(r'[^{}]*candidate-section-tooltip\s*\{([^}]*)\}', public_css)
        self.assertEqual(len(rules), 1)
        self.assertIn('right: 10px', rules[0])
        self.assertNotRegex(rules[0], r'background|border|font|shadow|color')

    def test_accessible_method_controls_reuse_existing_candidate_markup(self):
        tree = self.document()
        controls = tree.xpath('.//button[@class="candidate-section-info"]')
        self.assertEqual(len(controls), 4)
        for control in controls:
            self.assertEqual(control.get("type"), "button")
            self.assertEqual(control.text, "i")
            self.assertTrue(control.get("aria-label"))
            note = tree.get_element_by_id(control.get("aria-describedby"))
            self.assertEqual(note.get("class"), "candidate-section-tooltip")
            self.assertEqual(note.get("role"), "tooltip")
            self.assertIs(control.getparent(), note.getparent())
            self.assertIn("candidate-section-info-wrap", control.getparent().get("class"))
        for provider in PROVIDERS:
            card = self.card(provider)
            self.assertIn("candidate-panel", card.get("class").split())
            self.assertTrue(card.xpath('./header[@class="candidate-panel-head"]//span[contains(@class,"candidate-panel-info-wrap")]'))
            self.assertTrue(card.xpath('./div[@class="candidate-panel-body"]'))
        css = (ROOT / "assets/candidate-page.css").read_text(encoding="utf-8")
        self.assertIn("candidate-section-info:focus-visible", css)
        self.assertIn("candidate-section-info-wrap:focus-within .candidate-section-tooltip", css)
        self.assertNotIn("candidate-public-signals-method", css)
        self.assertNotIn("candidate-public-signal-info", css)
        self.assertFalse(tree.xpath('.//details'))

    def test_methodology_and_provenance_are_only_in_native_tooltips(self):
        self.bluesky_observed()
        for lang in ("fr", "en"):
            for provider in PROVIDERS:
                card = self.card(provider, lang)
                body = card.xpath('./div[@class="candidate-panel-body"]')[0]
                tooltip = card.xpath('.//span[@role="tooltip"]')[0]
                self.assertTrue(tooltip.text_content())
                self.assertIn(self.data[provider]["observed_at"], html.tostring(tooltip).decode())
                self.assertFalse(body.xpath('.//*[@role="tooltip"]'))
                self.assertFalse(body.xpath('.//details|.//time|.//*[@data-observed-at]'))
            poly_body = self.card("polymarket", lang).xpath('./div[@class="candidate-panel-body"]')[0].text_content()
            self.assertNotIn("second tour", poly_body)
            self.assertNotIn("runoff", poly_body)
            self.assertNotIn("FR27", poly_body)
        self.assertIn("three significant figures", self.card("youtube", "en").xpath('.//*[@role="tooltip"]')[0].text_content())
        self.assertIn("persistent identity", self.card("bluesky", "en").xpath('.//*[@role="tooltip"]')[0].text_content())

    def test_section_methodology_uses_native_info_without_visible_explanatory_line(self):
        for lang in ("fr", "en"):
            tree = self.document(lang)
            self.assertFalse(tree.xpath('./p|./details'))
            note = tree.get_element_by_id("public-signals-note")
            self.assertEqual(note.get("role"), "tooltip")
            self.assertIn("ne mesurent pas la même chose" if lang == "fr" else "do not measure the same thing", note.text_content())

    def test_unavailable_states_have_no_redundant_unit_or_empty_spacers(self):
        for status in ("unavailable_no_account", "unavailable_account_missing", "unavailable_public_web_opt_out"):
            self.data["bluesky"]["status"] = status
            for lang in ("fr", "en"):
                body = self.card("bluesky", lang).xpath('./div[@class="candidate-panel-body"]')[0]
                self.assertFalse(body.xpath('./p[@class="candidate-public-signal-unit"]'))
                self.assertFalse(body.xpath('./p[@class="candidate-public-signal-support"]'))
                self.assertFalse(body.xpath('.//a'))
        for provider in PROVIDERS:
            self.assertFalse([p for p in self.card(provider).xpath('.//p') if not p.text_content().strip()])

    def test_compact_card_geometry_uses_existing_kpi_type_without_minimum_heights(self):
        css = (ROOT / "assets/candidate-page.css").read_text(encoding="utf-8")
        public_css = css[css.index("/* Public sources reuse candidate panels"):]
        self.assertIn("font-size: var(--fr27-num-kpi)", public_css)
        self.assertNotIn("min-height", public_css)
        self.assertNotIn("clamp(", public_css)

    def test_no_movement_or_sparklines_without_supplied_history(self):
        for lang in ("fr", "en"):
            self.assertNotRegex(self.render(lang), r'<(?:svg|canvas|progress|meter)\b|data-(?:delta|trend|movement|sparkline)=')

    def test_no_optional_social_accounts_still_has_three_cards(self):
        self.data.pop("youtube")
        self.data.pop("bluesky")
        self.assertEqual(self.document().xpath('.//article/@data-provider'), PROVIDERS)

    def test_source_observation_times_remain_distinct(self):
        for key in ("polymarket", "youtube", "bluesky"):
            self.assertIn(self.data[key]["observed_at"], self.render())
        self.assertNotIn("attention-history", self.render())

    def test_rendering_preserves_projection_and_source_artifacts(self):
        paths = [ROOT / name for name in ("candidate_attention.json", "candidate_polymarket.json",
                                         "candidate_youtube.json", "candidate_bluesky.json",
                                         "candidate_polymarket_history.json", "candidate_youtube_history.json",
                                         "candidate_bluesky_history.json", "candidates/marine-le-pen/data.json")]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        projection = copy.deepcopy(self.data)
        self.render(); self.render("en")
        self.assertEqual(self.data, projection)
        self.assertEqual(before, [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths])


class PublicSignalMovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = reference.load_sources(ROOT)
        cls.payload = reference.build_projection(cls.sources, ROOT)
        cls.histories = trend.load_histories(ROOT)

    def setUp(self):
        self.data = copy.deepcopy(self.payload)
        self.history = copy.deepcopy(self.histories)

    def card(self, provider, lang="fr"):
        tree = html.fromstring(reference.render_public_signals(self.data, lang, self.history))
        return tree.xpath(f'.//article[@data-provider="{provider}"]')[0]

    def fixture(self, provider, value, baseline):
        row = self.data[provider]
        row["status"] = "observed"
        field = trend.PROVIDERS[provider][2]
        row[field] = value
        if provider == "youtube":
            row["hidden_subscriber_count"] = False
        if provider == "bluesky":
            row.update(did="did:plc:" + "a" * 24, handle="official.example.fr",
                       profile_url="https://bsky.app/profile/did:plc:" + "a" * 24)
        identities = {old: row[new] for old, new in trend.PROVIDERS[provider][3]}
        current = instant(row["observed_at"])
        points = [{"observed_at": iso(current - timedelta(days=days)), field: v}
                  for days, v in [(d, baseline if d else value) for d in range(8, -1, -1)]]
        if provider == "polymarket":
            for point in points:
                point["source"] = "fr27_snapshot"
        self.history[provider][self.data["candidate_id"]] = dict(identities, points=points)

    def change(self, provider, lang="fr"):
        return self.card(provider, lang).xpath('.//p[@class="candidate-public-signal-change"]')

    def test_polymarket_positive_negative_zero_in_both_locales(self):
        for value, baseline, french, english in [(.459, .421, "+3,8 pts · 7 j", "+3.8 pts · 7d"),
                (.400, .421, "−2,1 pts · 7 j", "−2.1 pts · 7d"),
                (.421, .421, "0,0 pt · 7 j", "0.0 pt · 7d")]:
            self.fixture("polymarket", value, baseline)
            for lang, expected in (("fr", french), ("en", english)):
                self.assertEqual(self.change("polymarket", lang)[0].xpath('./span[@aria-hidden="true"]')[0].text, expected)
                self.assertIn("points", self.change("polymarket", lang)[0].xpath('./span[@class="visually-hidden"]')[0].text)
                self.assertNotIn("%", self.change("polymarket", lang)[0].xpath('./span[@aria-hidden="true"]')[0].text)

    def assert_current_provider(self, provider):
        snapshot = self.sources[f"candidate_{provider}"]
        module, _, field, _ = trend.PROVIDERS[provider]
        for row in snapshot["candidates"]:
            with self.subTest(provider=provider, candidate=row["candidate_id"]):
                current = dict(row, observed_at=snapshot["observed_at"])
                history = self.histories[provider][row["candidate_id"]]
                unavailable = row["status"] != "observed" or row.get(field) is None
                baseline = None if unavailable else module.derive_delta(history, 7)
                for lang in ("fr", "en"):
                    rendered = trend.render_movement(provider, row["candidate_id"], current, self.histories, lang)
                    if baseline is None:
                        self.assertEqual(rendered, "")
                        continue
                    self.assertIn(trend.movement_text(provider, baseline, lang)[0], html.fromstring(rendered).text_content())
                    self.assertEqual(history["points"][-1][field], row[field])
                    self.assertEqual(history["points"][-1]["observed_at"], snapshot["observed_at"])
                    expected_chart = trend.render_trendline(history["points"], field, "test",
                        eligible=True, probability=provider == "polymarket")
                    self.assertEqual("<svg" in rendered, bool(expected_chart))
                    if expected_chart:
                        tree = html.fromstring(rendered)
                        self.assertEqual(tree.xpath('.//circle[@class="candidate-chart-point candidate-public-signal-current"]/@cx'), ["236.00"])
                payload = {"candidate_id": row["candidate_id"], provider: current}
                projection_file = ROOT / "candidates" / row["candidate_id"] / "data.json"
                if projection_file.exists():
                    projected = json.loads(projection_file.read_text(encoding="utf-8"))[provider]
                    self.assertEqual(projected[field], row[field])
                    self.assertEqual(projected["status"], row["status"])
                    self.assertEqual(projected["observed_at"], snapshot["observed_at"])
                if payload is not None and not unavailable:
                    for lang in ("fr", "en"):
                        card = html.fromstring(reference.render_public_signals(payload, lang, self.histories)).xpath(f'.//article[@data-provider="{provider}"]')[0]
                        value = card.xpath('.//p[@class="candidate-public-signal-value"]')[0].text_content()
                        expected = (f"{row[field] * 100:.1f}".replace(".", ",") + "\u00a0%" if lang == "fr" else f"{row[field] * 100:.1f}%") if provider == "polymarket" else reference._public_signal_number(row[field], lang)
                        self.assertEqual(value, expected)

    def test_current_polymarket_snapshot_parity_and_complete_reviewed_universe(self):
        from candidate_polymarket import validate_candidate_polymarket
        snapshot = self.sources["candidate_polymarket"]
        ids = {r["candidate_id"] for r in self.sources["candidate_candidacy_status"]["candidates"]}
        validate_candidate_polymarket(snapshot, mapping=self.sources["polymarket_candidate_markets"], candidate_ids=ids)
        self.assertEqual({r["candidate_id"] for r in snapshot["candidates"]}, ids)
        self.assert_current_provider("polymarket")

    def test_current_youtube_and_bluesky_follow_available_history(self):
        for provider in ("youtube", "bluesky"):
            self.assert_current_provider(provider)

    def test_explicit_immature_histories_render_no_fake_movement(self):
        for provider in ("youtube", "bluesky"):
            self.fixture(provider, 123000, 120000)
            self.history[provider][self.data["candidate_id"]]["points"] = self.history[provider][self.data["candidate_id"]]["points"][-6:]
            self.assertFalse(self.change(provider))
            self.assertFalse(self.card(provider).xpath('.//svg'))

    def test_mature_irregular_count_histories_use_latest_at_or_before_anchor(self):
        for provider in ("youtube", "bluesky"):
            self.fixture(provider, 1420, 1000)
            points = self.history[provider][self.data["candidate_id"]]["points"]
            del points[1]  # No observation exactly seven days earlier.
            points[1][trend.PROVIDERS[provider][2]] = 1100  # Too recent for the baseline.
            self.assertEqual(self.change(provider, "en")[0].xpath('./span[@aria-hidden="true"]')[0].text, "+420 · 7d")
            self.assertTrue(self.card(provider).xpath('.//svg'))

    def test_sparse_chart_keeps_valid_numeric_movement(self):
        self.fixture("polymarket", .459, .421)
        row = self.history["polymarket"][self.data["candidate_id"]]
        row["points"] = [row["points"][0], *row["points"][-2:]]
        for lang in ("fr", "en"):
            self.assertTrue(self.change("polymarket", lang))
            self.assertFalse(self.card("polymarket", lang).xpath('.//svg'))

    def test_future_youtube_baseline_activates_without_flag(self):
        self.fixture("youtube", 217000, 214000)
        self.data["youtube"].update(recent_window_complete=True, uploads_last_7d=9)
        for lang, expected in (("fr", "+3\u202f000 · 7 j"), ("en", "+3,000 · 7d")):
            card = self.card("youtube", lang)
            self.assertEqual(self.change("youtube", lang)[0].xpath('./span[@aria-hidden="true"]')[0].text, expected)
            self.assertIn("abonnés" if lang == "fr" else "subscribers", self.change("youtube", lang)[0].xpath('./span[@class="visually-hidden"]')[0].text)
            self.assertEqual(len(card.xpath('.//svg')), 1)
            self.assertIn("9 vidéos" if lang == "fr" else "9 uploads", card.text_content())
            self.assertNotIn("217,000.0", card.text_content())

    def test_future_bluesky_baseline_activates_and_preserves_handle(self):
        self.fixture("bluesky", 54158, 53738)
        for lang, expected in (("fr", "+420 · 7 j"), ("en", "+420 · 7d")):
            card = self.card("bluesky", lang)
            self.assertEqual(self.change("bluesky", lang)[0].xpath('./span[@aria-hidden="true"]')[0].text, expected)
            self.assertEqual(len(card.xpath('.//svg')), 1)
            self.assertIn("@official.example.fr", card.text_content())
            self.assertNotIn("did:plc:", card.text_content())
            self.assertIn("abonnés" if lang == "fr" else "followers", self.change("bluesky", lang)[0].xpath('./span[@class="visually-hidden"]')[0].text)

    def test_count_negative_zero_and_accessible_loss_semantics(self):
        for provider in ("youtube", "bluesky"):
            self.fixture(provider, 1000, 1420)
            self.assertEqual(self.change(provider)[0].xpath('./span[@aria-hidden="true"]')[0].text, "−420 · 7 j")
            self.assertIn("en moins", self.change(provider)[0].xpath('./span[@class="visually-hidden"]')[0].text)
            self.assertIn("fewer", self.change(provider, "en")[0].xpath('./span[@class="visually-hidden"]')[0].text)
            self.fixture(provider, 1000, 1000)
            self.assertEqual(self.change(provider, "en")[0].xpath('./span[@aria-hidden="true"]')[0].text, "0 · 7d")

    def test_youtube_hidden_null_and_uploads_never_supply_baseline(self):
        self.fixture("youtube", 217000, 214000)
        for hidden in (True, False):
            self.data["youtube"].update(hidden_subscriber_count=hidden, subscriber_count=None)
            self.assertFalse(self.change("youtube"))
            self.assertFalse(self.card("youtube").xpath('.//svg'))
        self.data["youtube"].update(hidden_subscriber_count=False, subscriber_count=217000, uploads_last_7d=100)
        self.history["youtube"][self.data["candidate_id"]]["points"] = self.history["youtube"][self.data["candidate_id"]]["points"][-1:]
        self.assertFalse(self.change("youtube"))

    def test_unavailable_providers_and_bluesky_opt_out_have_no_trend(self):
        for provider in ("polymarket", "youtube", "bluesky"):
            self.data[provider]["status"] = "unavailable_no_account"
            self.assertFalse(self.card(provider).xpath('.//svg'))
            self.assertFalse(self.change(provider))
        self.data["bluesky"]["status"] = "unavailable_public_web_opt_out"
        self.assertFalse(self.card("bluesky").xpath('.//svg|.//a'))

    def test_identity_and_terminal_snapshot_mismatch_fail_closed(self):
        for provider in ("polymarket", "youtube", "bluesky"):
            self.data = copy.deepcopy(self.payload)
            self.history = copy.deepcopy(self.histories)
            self.fixture(provider, .459 if provider == "polymarket" else 217000, .421 if provider == "polymarket" else 214000)
            key = trend.PROVIDERS[provider][3][0][0]
            self.history[provider][self.data["candidate_id"]][key] = "wrong"
            with self.assertRaisesRegex(HistoryError, "identity"):
                self.card(provider)
            self.history = copy.deepcopy(self.histories)
        self.data = copy.deepcopy(self.payload)
        self.history = copy.deepcopy(self.histories)
        self.fixture("polymarket", .459, .421)
        self.history["polymarket"][self.data["candidate_id"]]["points"][-1]["implied_probability"] = .9
        with self.assertRaisesRegex(HistoryError, "authoritative"):
            self.card("polymarket")

    def test_native_tooltips_explain_anchor_units_independent_scales(self):
        for provider in ("polymarket", "youtube", "bluesky"):
            for lang in ("fr", "en"):
                card = self.card(provider, lang)
                tooltip = card.xpath('.//span[@role="tooltip"]')[0].text_content()
                self.assertIn("sept jours" if lang == "fr" else "seven days earlier", tooltip)
                self.assertIn("30 jours" if lang == "fr" else "30 days", tooltip)
                self.assertIn("propre échelle" if lang == "fr" else "own scale", tooltip)
                self.assertIn("dates UTC" if lang == "fr" else "UTC dates", tooltip)
                body = card.xpath('./div[@class="candidate-panel-body"]')[0].text_content()
                self.assertNotIn("propre échelle", body)
                self.assertNotIn("own scale", body)

    def test_real_bilingual_trend_structure_parity(self):
        cards = [self.card("polymarket", lang) for lang in ("fr", "en")]
        self.assertEqual([n.tag for n in cards[0].iter()], [n.tag for n in cards[1].iter()])
        self.assertTrue(cards[0].xpath('.//svg/@aria-label')[0])
        self.assertEqual(cards[0].xpath('.//g/@aria-hidden'), ["true"])

    def test_rendering_does_not_modify_inputs_or_project_raw_history(self):
        before = copy.deepcopy((self.data, self.history))
        rendered = reference.render_public_signals(self.data, "en", self.history)
        self.assertEqual((self.data, self.history), before)
        self.assertNotIn('"points":', rendered)
        self.assertNotIn('latest_source_point', rendered)
        self.assertNotIn('retention_days', rendered)
        self.assertNotIn('2026-07-', rendered)
        self.assertNotIn('history', reference.SOURCE_FILES)
        self.assertFalse(any(k.endswith('_history') and k.startswith('candidate_p') for k in reference.SOURCE_FILES))
        css = (ROOT / 'assets/candidate-page.css').read_text()
        public_css = css[css.index('/* Public sources reuse candidate panels'):]
        self.assertIn('align-items: stretch', public_css)
        self.assertNotIn('min-height', public_css)
        self.assertNotRegex(public_css, r'green|red|gradient|box-shadow')


class PublicSignalTrendlineTests(unittest.TestCase):
    def points(self, values, days=None):
        end = instant("2026-10-17T12:00:00Z")
        days = days or list(range(len(values) - 1, -1, -1))
        return [{"observed_at": iso(end - timedelta(days=d)), "followers_count": value}
                for d, value in zip(days, values)]

    def render(self, points, label='Trend "sample" <safe>', eligible=True):
        return trend.render_trendline(points, 'followers_count', label, eligible=eligible)

    def test_one_point_and_ineligible_history_have_no_chart(self):
        self.assertEqual(self.render(self.points([1])), '')
        self.assertEqual(self.render(self.points([1, 2], [8, 0]), eligible=False), '')
        self.assertEqual(self.render(self.points([1, 2], [6, 0])), '')
        self.assertEqual(self.render([]), '')

    def test_chronological_sort_and_deterministic_coordinates(self):
        points = self.points([1, 2, 3], [8, 1, 0])
        self.assertEqual(self.render(points), self.render(list(reversed(points))))
        self.assertEqual(self.render(points), self.render(points))

    def test_flat_line_is_centered(self):
        svg = html.fromstring(self.render(self.points([42] * 9)))
        coords = svg.xpath('.//polyline/@points')[0].split()
        self.assertTrue(all(pair.endswith(',22.00') for pair in coords))

    def test_increasing_decreasing_and_safe_bounds(self):
        for values in (list(range(9)), list(reversed(range(9))), [2**53 - 1] * 9):
            svg = html.fromstring(self.render(self.points(values)))
            coords = [tuple(map(float, p.split(','))) for p in svg.xpath('.//polyline/@points')[0].split()]
            self.assertTrue(all(math.isfinite(x) and 4 <= x <= 236 and 4 <= y <= 40 for x, y in coords))
            self.assertEqual(coords[0][0], 4)
            self.assertEqual(coords[-1][0], 236)
            if values[0] != values[-1]:
                self.assertEqual(coords[0][1] > coords[-1][1], values[0] < values[-1])

    def test_irregular_time_spacing_and_missing_dates_not_synthesized(self):
        points = self.points(list(range(10)), [15, 14, 13, 12, 11, 10, 9, 8, 1, 0])
        svg = html.fromstring(self.render(points))
        lines = svg.xpath('.//polyline/@points')
        dots = svg.xpath('.//circle[@class="candidate-public-signal-trend-point"]')
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0].split()), 8)
        self.assertEqual(len(dots), 2)
        self.assertAlmostEqual(float(dots[0].get('cx')), 4 + 232 * 14 / 15, places=2)
        self.assertEqual(dots[-1].get('cx'), '236.00')

    def test_gap_singleton_is_actual_point_not_connected_line(self):
        svg = html.fromstring(self.render(self.points(list(range(9)), [12, 11, 10, 9, 8, 7, 6, 5, 0])))
        self.assertEqual(len(svg.xpath('.//circle[@class="candidate-public-signal-trend-point"]')), 1)
        self.assertEqual(len(svg.xpath('.//polyline')), 1)
        self.assertEqual(svg.xpath('.//circle[@class="candidate-chart-point candidate-public-signal-current"]/@cx'), ['236.00'])

    def test_only_last_thirty_days_render(self):
        svg = html.fromstring(self.render(self.points(list(range(41)))))
        self.assertEqual(len(svg.xpath('.//polyline/@points')[0].split()), 31)

    def probability_svg(self, values, days=None):
        points = [dict(observed_at=p['observed_at'], implied_probability=p['followers_count'])
                  for p in self.points(values, days)]
        return html.fromstring(trend.render_trendline(points, 'implied_probability',
                               'Probability in native units', eligible=True, probability=True))

    def test_two_point_run_uses_markers_not_a_detached_stroke(self):
        svg = html.fromstring(self.render(self.points(list(range(9)), [11, 10, 9, 8, 7, 6, 5, 1, 0])))
        self.assertEqual(len(svg.xpath('.//polyline')), 1)
        self.assertEqual(len(svg.xpath('.//polyline/@points')[0].split()), 7)
        self.assertEqual(len(svg.xpath('.//circle[@class="candidate-public-signal-trend-point"]')), 2)

    def test_three_point_run_is_a_line(self):
        svg = html.fromstring(self.render(self.points(list(range(10)), [12, 11, 10, 9, 8, 7, 6, 2, 1, 0])))
        self.assertEqual([len(x.split()) for x in svg.xpath('.//polyline/@points')], [7, 3])
        self.assertFalse(svg.xpath('.//circle[@class="candidate-public-signal-trend-point"]'))

    def test_sparse_window_suppresses_chart_without_changing_valid_delta(self):
        points = self.points([10, 11, 12], [9, 1, 0])
        self.assertIsNotNone(trend.delta(points, 'followers_count', 7))
        self.assertEqual(self.render(points), '')
        # Seven observed dates alone do not justify a mostly empty 30-day chart.
        self.assertEqual(self.render(self.points(list(range(7)), [30, 29, 28, 27, 26, 25, 0])), '')

    def test_missing_utc_date_breaks_regardless_of_sampling_jitter(self):
        points = self.points(list(range(10)), [10, 9, 8, 7, 6, 5, 4, 3, 1, 0])
        for seconds in (-5, 5):
            adjusted = copy.deepcopy(points)
            adjusted[-2]['observed_at'] = iso(instant(adjusted[-2]['observed_at']) + timedelta(seconds=seconds))
            svg = html.fromstring(self.render(adjusted))
            self.assertEqual(len(svg.xpath('.//polyline')), 1)
            self.assertEqual(len(svg.xpath('.//circle[@class="candidate-public-signal-trend-point"]')), 2)

    def test_consecutive_utc_dates_still_require_at_most_36_hours(self):
        points = self.points(list(range(10)))
        points[-2]['observed_at'] = iso(instant(points[-2]['observed_at']) - timedelta(hours=11))
        points[-1]['observed_at'] = iso(instant(points[-1]['observed_at']) + timedelta(hours=11))
        svg = html.fromstring(self.render(points))
        self.assertEqual(len(svg.xpath('.//circle[@class="candidate-public-signal-trend-point"]')), 1)

    def test_probability_minimum_span_prevents_tiny_change_amplification(self):
        for start in (0, .001, .5, .999):
            svg = self.probability_svg([start] * 8 + [start + .0005])
            ys = [float(pair.split(',')[1]) for pair in svg.xpath('.//polyline/@points')[0].split()]
            # 0.05 percentage point / five-percentage-point domain * 36 SVG units.
            self.assertAlmostEqual(max(ys) - min(ys), .36, places=2)

    def test_zero_and_one_flat_probability_stay_centered(self):
        for value in (0, .001, 1):
            svg = self.probability_svg([value] * 9)
            self.assertTrue(all(pair.endswith(',22.00') for pair in svg.xpath('.//polyline/@points')[0].split()))

    def test_probability_domain_bounds_including_full_native_range(self):
        for values in ([0] * 8 + [1], [.99] * 8 + [1], [0] * 8 + [.01]):
            svg = self.probability_svg(values)
            ys = [float(pair.split(',')[1]) for pair in svg.xpath('.//polyline/@points')[0].split()]
            self.assertTrue(all(4 <= y <= 40 and math.isfinite(y) for y in ys))

    def test_count_scale_does_not_inherit_probability_minimum(self):
        for baseline in (100, 2**53 - 2):
            svg = html.fromstring(self.render(self.points([baseline] * 8 + [baseline + 1])))
            ys = [float(pair.split(',')[1]) for pair in svg.xpath('.//polyline/@points')[0].split()]
            self.assertAlmostEqual(max(ys) - min(ys), 30, places=2)
            self.assertTrue(all(4 <= y <= 40 for y in ys))

    def test_current_ring_matches_last_observation_and_scale(self):
        svg = self.probability_svg([.01] * 8 + [.011])
        terminal = svg.xpath('.//circle[@class="candidate-chart-point candidate-public-signal-current"]')[0]
        last_pair = svg.xpath('.//polyline/@points')[0].split()[-1]
        self.assertEqual(last_pair, terminal.get('cx') + ',' + terminal.get('cy'))
        self.assertEqual(terminal.get('cx'), '236.00')

    def test_fully_observed_window_has_no_extra_samples_or_breaks(self):
        svg = html.fromstring(self.render(self.points(list(range(31)))))
        self.assertEqual(len(svg.xpath('.//polyline')), 1)
        self.assertEqual(len(svg.xpath('.//polyline/@points')[0].split()), 31)
        self.assertFalse(svg.xpath('.//circle[@class="candidate-public-signal-trend-point"]'))
        self.assertEqual(len(svg.xpath('.//circle')), 1)  # Terminal annotation, not another sample.

    def test_older_baseline_but_only_one_visible_point_has_no_chart(self):
        self.assertEqual(self.render(self.points([1, 2], [40, 0])), '')

    def test_duplicate_timestamps_rejected(self):
        with self.assertRaisesRegex(HistoryError, 'duplicate'):
            self.render(self.points([1, 2], [0, 0]))

    def test_invalid_numbers_and_timestamps_fail_closed(self):
        for value in (float('nan'), float('inf'), -1, 2**53, True, 1.1):
            with self.assertRaises(HistoryError):
                self.render(self.points([1, value], [8, 0]))
        with self.assertRaises(HistoryError):
            self.render([dict(observed_at='bad', followers_count=1)])

    def test_accessible_escaped_label_and_no_runtime_chart_library(self):
        output = self.render(self.points([1] * 9))
        svg = html.fromstring(output)
        self.assertEqual(svg.get('aria-label'), 'Trend "sample" <safe>')
        self.assertEqual(svg.get('role'), 'img')
        self.assertEqual(svg.get('focusable'), 'false')
        self.assertEqual(svg.xpath('./g/@aria-hidden'), ['true'])
        self.assertNotRegex(output, r'<script|foreignObject|NaN|Infinity|onload=')
        self.assertIn('class="candidate-chart-line"', output)


if __name__ == "__main__":
    unittest.main()
