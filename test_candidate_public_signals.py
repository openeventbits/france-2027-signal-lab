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
        self.assertEqual(self.data["polymarket"]["implied_probability"], 0.4585)
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
        return html.fromstring(reference.render_html(self.data, lang=lang))

    def test_wikipedia_section_matches_head_exactly_except_relocated_polymarket(self):
        for lang in ("fr", "en"):
            rendered = reference.render_html(self.data, lang=lang).decode("utf-8")
            route = ("en/" if lang == "en" else "") + "candidates/marine-le-pen/index.html"
            original = subprocess.check_output(["git", "show", "HEAD:" + route]).decode("utf-8")
            pattern = r'<section class="candidate-section" id="attention".*?</section>'
            expected = re.search(pattern, original, re.S).group()
            expected = re.sub(r'      <aside class="candidate-polymarket".*?</aside>\n', "", expected, flags=re.S)
            self.assertEqual(re.search(pattern, rendered, re.S).group(), expected)

    def test_wikipedia_existing_values_chart_and_methodology_preserved(self):
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

    def test_responsive_geometry_uses_existing_breakpoints(self):
        css = (ROOT / "assets/candidate-page.css").read_text(encoding="utf-8")
        self.assertRegex(css, r'candidate-public-signals-grid\s*\{[^}]*repeat\(2, minmax\(0, 1fr\)\)')
        self.assertRegex(css, r'@media \(min-width: 1350px\)\s*\{\s*\.candidate-page \.candidate-public-signals-grid[^}]*repeat\(3, minmax\(0, 1fr\)\)')
        self.assertRegex(css, r'@media \(max-width: 759\.98px\)\s*\{\s*\.candidate-page \.candidate-public-signals-grid[^}]*grid-template-columns: minmax\(0, 1fr\)')
        self.assertIn("overflow-wrap: anywhere", css)

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
        self.assertNotIn("candidate-section-tooltip", public_css)

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
                  for days, v in [(8, baseline), (2, baseline), (0, value)]]
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

    def test_current_snapshot_headline_and_terminal_point_not_latest_clob_quote(self):
        card = self.card("polymarket")
        self.assertEqual(card.xpath('.//p[@class="candidate-public-signal-value"]')[0].text_content(), "45,9\u00a0%")
        series, field, _ = trend.current_series("polymarket", self.data["candidate_id"], self.data["polymarket"], self.history)
        self.assertEqual(series[-1][field], self.data["polymarket"][field])
        self.assertEqual(series[-1]["source"], "fr27_snapshot")
        svg = card.xpath('.//*[local-name()="svg"]')[0]
        expected = html.fromstring(trend.render_movement("polymarket", self.data["candidate_id"], self.data["polymarket"], self.history, "fr"))
        self.assertEqual(svg.xpath('.//polyline/@points'), expected.xpath('.//polyline/@points'))
        self.assertTrue(svg.xpath('.//polyline/@points')[-1].split()[-1].startswith("236.00,"))

    def test_all_real_mapped_polymarket_rows_have_delta_and_chart(self):
        snapshot = self.sources["candidate_polymarket"]
        observed = [r for r in snapshot["candidates"] if r["status"] == "observed"]
        self.assertEqual(len(observed), 38)
        for row in observed:
            current = dict(row, observed_at=snapshot["observed_at"])
            rendered = trend.render_movement("polymarket", row["candidate_id"], current, self.histories, "fr")
            self.assertIn('class="candidate-public-signal-change"', rendered)
            self.assertIn('<svg', rendered)

    def test_real_youtube_and_bluesky_have_no_movement_or_chart(self):
        for provider in ("youtube", "bluesky"):
            snapshot = self.sources[f"candidate_{provider}"]
            for row in snapshot["candidates"]:
                current = dict(row, observed_at=snapshot["observed_at"])
                self.assertEqual(trend.render_movement(provider, row["candidate_id"], current, self.histories, "en"), "")

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
            self.fixture(provider, .459 if provider == "polymarket" else 217000, .421 if provider == "polymarket" else 214000)
            key = trend.PROVIDERS[provider][3][0][0]
            self.history[provider][self.data["candidate_id"]][key] = "wrong"
            with self.assertRaisesRegex(HistoryError, "identity"):
                self.card(provider)
            self.history = copy.deepcopy(self.histories)
        self.data = copy.deepcopy(self.payload)
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
                self.assertIn("48 h" if lang == "fr" else "48 hours", tooltip)
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
        self.assertIn('align-items: start', public_css)
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
        svg = html.fromstring(self.render(self.points([10, 20, 30, 40], [8, 7, 1, 0])))
        lines = svg.xpath('.//polyline/@points')
        self.assertEqual(len(lines), 2)
        self.assertEqual(sum(len(line.split()) for line in lines), 4)
        self.assertEqual(lines[0].split()[1].split(',')[0], '33.00')
        self.assertEqual(lines[1].split()[0].split(',')[0], '207.00')

    def test_gap_singleton_is_actual_point_not_connected_line(self):
        svg = html.fromstring(self.render(self.points([10, 20, 30], [8, 1, 0])))
        self.assertEqual(len(svg.xpath('.//circle')), 1)
        self.assertEqual(len(svg.xpath('.//polyline')), 1)

    def test_only_last_thirty_days_render(self):
        svg = html.fromstring(self.render(self.points(list(range(41)))))
        self.assertEqual(len(svg.xpath('.//polyline/@points')[0].split()), 31)

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
