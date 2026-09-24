"""Contracts for the fixed Marine Le Pen candidate reference page."""

from __future__ import annotations

import html as html_module
import json
import re
import unittest
from pathlib import Path

import build_candidate_reference as reference


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "candidates" / "marine-le-pen" / "data.json"
HTML_PATH = ROOT / "candidates" / "marine-le-pen" / "index.html"
CSS_PATH = ROOT / "assets" / "candidate-page.css"
SHELL_CSS_PATH = ROOT / "assets" / "candidate-page-shell.css"
JS_PATH = ROOT / "assets" / "candidate-page.js"


class CandidateReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = reference.load_sources(ROOT)
        cls.projection = reference.build_projection(cls.sources, ROOT)
        cls.published = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        visible_html = re.sub(
            r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
            " ",
            cls.html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cls.visible_text = html_module.unescape(
            re.sub(r"<[^>]+>", " ", visible_html)
        )
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.shell_css = SHELL_CSS_PATH.read_text(encoding="utf-8")
        cls.javascript = JS_PATH.read_text(encoding="utf-8")

    def test_candidate_search_head_is_indexable_and_uses_root_brand_contract(self):
        root_html = (ROOT / "index.html").read_text(encoding="utf-8")

        favicon = re.search(
            r'<link rel="icon" type="image/svg\+xml" '
            r'href="data:image/svg\+xml;base64,[^"]+">',
            root_html,
        )
        self.assertIsNotNone(favicon)

        rendered_fr = reference.render_html(
            self.projection,
            reference.derive_hud_metrics(self.sources),
            lang="fr",
        ).decode("utf-8")

        rendered_en = reference.render_html(
            self.projection,
            reference.derive_hud_metrics(self.sources),
            lang="en",
        ).decode("utf-8")

        for rendered, canonical in (
            (
                rendered_fr,
                "https://france2027.app/candidates/marine-le-pen/",
            ),
            (
                rendered_en,
                "https://france2027.app/en/candidates/marine-le-pen/",
            ),
        ):
            self.assertIn(
                '<meta name="robots" '
                'content="index,follow,max-image-preview:large">',
                rendered,
            )
            self.assertIn(favicon.group(0), rendered)
            self.assertIn(
                f'<link rel="canonical" href="{canonical}">',
                rendered,
            )
            self.assertIn(
                '<link rel="alternate" hreflang="fr" '
                'href="https://france2027.app/candidates/marine-le-pen/">',
                rendered,
            )
            self.assertIn(
                '<link rel="alternate" hreflang="en" '
                'href="https://france2027.app/en/candidates/marine-le-pen/">',
                rendered,
            )
            self.assertIn(
                '<link rel="alternate" hreflang="x-default" '
                'href="https://france2027.app/candidates/marine-le-pen/">',
                rendered,
            )
            self.assertIn(
                '<meta property="og:site_name" '
                'content="France 2027 Signal Lab">',
                rendered,
            )
            self.assertIn(
                '<meta property="og:image" content="',
                rendered,
            )
            self.assertIn(
                '<meta name="twitter:card" '
                'content="summary_large_image">',
                rendered,
            )
            self.assertNotIn(
                'content="noindex,nofollow"',
                rendered,
            )

        synthetic = {
            "candidate": {
                "candidate_id": "gabriel-attal",
                "candidate_name": "Gabriel Attal",
            }
        }

        fr_contract = reference._candidate_locale_contract(
            synthetic,
            "fr",
        )
        en_contract = reference._candidate_locale_contract(
            synthetic,
            "en",
        )

        self.assertEqual(
            fr_contract["canonical"],
            "https://france2027.app/candidates/gabriel-attal/",
        )
        self.assertEqual(
            en_contract["canonical"],
            "https://france2027.app/en/candidates/gabriel-attal/",
        )
        self.assertIn(
            "Gabriel Attal",
            fr_contract["title"],
        )
        self.assertIn(
            "Gabriel Attal",
            en_contract["description"],
        )

    def test_generated_projection_and_html_are_current(self):
        self.assertEqual(
            DATA_PATH.read_bytes(),
            reference.serialize_projection(self.projection),
        )
        self.assertTrue(
            reference._newline_equivalent(
                HTML_PATH.read_bytes(),
                reference.render_html(self.projection),
            )
        )

    def test_generated_html_check_tolerates_only_line_ending_conversion(self):
        expected = b"<main>alpha\nbeta</main>"
        windows_checkout = b"<main>alpha\r\nbeta</main>"
        changed_content = b"<main>alpha\r\ngamma</main>"

        self.assertTrue(
            reference._newline_equivalent(windows_checkout, expected)
        )
        self.assertFalse(
            reference._newline_equivalent(changed_content, expected)
        )

    def test_canonical_identity_and_declared_status_are_locked(self):
        self.assertEqual(reference.CANDIDATE_ID, "marine-le-pen")
        self.assertEqual(self.published["candidate_id"], "marine-le-pen")
        self.assertEqual(self.published["candidate"]["candidate_id"], "marine-le-pen")
        self.assertEqual(self.published["candidate"]["candidate_name"], "Marine Le Pen")
        self.assertEqual(self.published["candidate"]["status"], "declared")
        self.assertNotIn("affiliation", self.published["candidate"])

    def test_projection_candidate_id_is_parameterized_and_active_scoped(self):
        explicit = reference.build_projection(
            self.sources,
            ROOT,
            candidate_id=reference.CANDIDATE_ID,
        )
        self.assertEqual(explicit, self.projection)

        registry = self.sources["candidate_candidacy_status"]
        hidden = next(
            candidate
            for candidate in registry["candidates"]
            if candidate["display_tier"] == "hidden"
        )

        with self.assertRaisesRegex(
            reference.CandidateReferenceError,
            "not in the active monitoring field",
        ):
            reference.build_projection(
                self.sources,
                ROOT,
                candidate_id=hidden["candidate_id"],
            )

    def test_current_polling_defaults_to_range_and_hypothesis_count(self):
        current = self.published["polling"]["current"]
        self.assertEqual(
            (current["range_min"], current["range_max"], current["hypothesis_count"]),
            (33, 36, 5),
        )
        self.assertIn("33–36% · 5 hypothèses", self.html)
        dossier = re.search(
            r'<dl class="candidate-dossier-metrics">(?P<body>.*?)</dl>',
            self.html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(dossier)
        self.assertIn("33–36% · 5 hypothèses", dossier.group("body"))
        self.assertNotIn(">36%<", dossier.group("body"))

        polling_section = self._section_html("polling", "media")
        readout = re.search(
            r'<div class="candidate-poll-readout">'
            r'<strong>(?P<range>.*?)</strong><span>(?P<hypotheses>.*?)</span></div>',
            polling_section,
        )
        self.assertIsNotNone(readout)
        self.assertEqual(readout.group("range"), "33–36%")
        self.assertEqual(readout.group("hypotheses"), "5 hypothèses")
        self.assertNotIn("·", readout.group(0))
        self.assertEqual(reference._hypothesis_text(1), "1 hypothèse")
        self.assertEqual(reference._hypothesis_text(2), "2 hypothèses")

    def test_poll_history_projection_data_is_unchanged_and_ordered(self):
        published = self.published["polling"]["first_round_history"]
        projected = self.projection["polling"]["first_round_history"]
        self.assertEqual(published["observation_count"], len(published["observations"]))
        self.assertEqual(published["observation_count"], projected["observation_count"])
        fields = (
            "pollster",
            "fieldwork_start",
            "fieldwork_end",
            "sample_size",
            "hypothesis_count",
            "selected_score",
            "range_min",
            "range_max",
            "source_urls",
        )
        self.assertEqual(
            [{field: item[field] for field in fields} for item in published["observations"]],
            [{field: item[field] for field in fields} for item in projected["observations"]],
        )

    def test_poll_history_has_real_accessible_tooltip_interaction(self):
        polling_section = self._section_html("polling", "media")
        self.assertIn("candidate-poll-history-panel", polling_section)
        self.assertIn("candidate-panel-info-wrap", polling_section)
        self.assertIn('aria-describedby="poll-history-note"', polling_section)
        self.assertIn('role="group" aria-label="Historique des scores publiés', polling_section)
        methodology = (
            "Chaque marque représente une observation publiée. Une barre verticale "
            "indique la fourchette entre hypothèses lorsqu’elle existe. Aucune moyenne, "
            "aucun lissage ni interpolation."
        )
        self.assertIn(methodology, polling_section)
        self.assertNotIn(
            f'<p class="candidate-method-note">{methodology}</p>',
            polling_section,
        )

        poll_renderer = self.javascript[
            self.javascript.index("const renderPollHistory"):
            self.javascript.index("const renderLineChart")
        ]
        for text in (
            'tooltip.className = "candidate-chart-tooltip"',
            "point.pollster",
            'candidateText("Terrain", "Fieldwork")',
            'candidateText("Fourchette publiée", "Published range")',
            'candidateText("Score exact de l’hypothèse sélectionnée", "Exact selected-hypothesis score")',
            'candidateText("Fourchette du scénario", "Scenario range")',
            "formatHypotheses(point.hypothesis_count)",
            'candidateText("échantillon", "sample")',
            'candidateText("Voir la source ↗", "View source ↗")',
            "tabindex: 0",
            'trigger.addEventListener("pointerenter"',
            'trigger.addEventListener("focus"',
            'trigger.addEventListener("keydown"',
            'trigger.setAttribute("target", "_blank")',
            'trigger.setAttribute("rel", "noopener noreferrer")',
        ):
            self.assertIn(text, poll_renderer)
        self.assertIn('"aria-describedby": tooltip.id', poll_renderer)
        self.assertIn('class: "candidate-chart-hit-target"', poll_renderer)
        self.assertIn('class: "candidate-chart-range-hit-target"', poll_renderer)

    def test_poll_history_keeps_fixed_honest_axis_and_discrete_marks(self):
        poll_renderer = self.javascript[
            self.javascript.index("const renderPollHistory"):
            self.javascript.index("const renderLineChart")
        ]
        self.assertIn("maxY: 50", poll_renderer)
        self.assertIn("yTicks: 5", poll_renderer)
        self.assertIn("height: 230", poll_renderer)
        self.assertNotIn("pathFor(", poll_renderer)
        self.assertNotIn("candidate-chart-line", poll_renderer)

    def test_media_pulse_is_coverage_share_and_reconciles(self):
        signals = next(
            item
            for item in self.sources["candidate_signals"]["candidates"]
            if item["candidate_id"] == reference.CANDIDATE_ID
        )
        media = self.published["media"]
        self.assertEqual(
            media["available_record_count"],
            signals["campaign_attention"]["record_count"],
        )
        self.assertEqual(media["summary"], signals["campaign_attention"])
        self.assertEqual(
            len({item["publisher"] for item in self._current_news_records()}),
            signals["campaign_attention"]["publisher_count"],
        )
        self.assertIn("PART DE LA COUVERTURE ÉLECTION + CAMPAGNE", self.html)
        self.assertIn("Il ne mesure ni soutien, ni approbation, ni sentiment, ni intention de vote", self.html)

    def test_media_top_row_preserves_summary_and_exposes_definition(self):
        media = self.published["media"]
        summary = media["summary"]
        self.assertEqual(summary["share"], 0.281)
        self.assertEqual(
            (
                summary["record_count"],
                summary["publisher_count"],
                summary["story_cluster_count"],
                summary["active_day_count"],
            ),
            (124, 44, 102, 7),
        )
        media_section = self._section_html("media", "agenda")
        self.assertIn('aria-describedby="media-pulse-note"', media_section)
        self.assertIn('id="media-pulse-note" role="tooltip"', media_section)
        self.assertIn(
            "Media Pulse mesure la part des articles associés à Marine Le Pen",
            media_section,
        )
        self.assertIn(
            "Il ne mesure ni soutien, ni approbation, ni sentiment, ni intention de vote.",
            media_section,
        )
        self.assertIn(
            "Part des articles associés à Marine Le Pen dans les périmètres "
            "« élection » et « campagne ».",
            media_section,
        )

    def test_media_history_projection_is_unchanged_and_ordered(self):
        published = self.published["media"]["recent_history"]
        projected = self.projection["media"]["recent_history"]
        self.assertEqual(len(published), 29)
        self.assertEqual(
            [
                {
                    "date": item["date"],
                    "share": item["share"],
                    "record_count": item["record_count"],
                    "publisher_count": item["publisher_count"],
                }
                for item in published
            ],
            [
                {
                    "date": item["date"],
                    "share": item["share"],
                    "record_count": item["record_count"],
                    "publisher_count": item["publisher_count"],
                }
                for item in projected
            ],
        )

    def test_media_history_has_compact_honest_axis_and_real_tooltip(self):
        renderer = self.javascript[
            self.javascript.index("const renderMediaHistory"):
            self.javascript.index("const renderAttentionHistory")
        ]
        for text in (
            "Math.ceil(maximumPercent / 10) * 10",
            "Math.min(100, Math.max(10",
            "maxY: ceilingPercent / 100",
            "height: 230",
            'tooltip.className = "candidate-chart-tooltip"',
            "formatDate(point.date)",
            'candidateText("Part quotidienne", "Daily share")',
            'candidateText("Articles associés", "Associated articles")',
            'candidateText("Éditeurs", "Publishers")',
            'candidateText("Observation indisponible", "Observation unavailable")',
            'class: "candidate-chart-hit-target"',
            'trigger.addEventListener("pointerenter"',
            'trigger.addEventListener("pointerdown"',
            'trigger.addEventListener("focus"',
            'trigger.addEventListener("keydown"',
            'event.key === "Escape"',
        ):
            self.assertIn(text, renderer)
        self.assertNotIn("1.08", renderer)
        self.assertNotIn("108%", renderer)
        self.assertIn("segments.forEach", renderer)
        self.assertIn("if (value === null)", renderer)
        self.assertIn("const available = share !== null", renderer)
        self.assertIn("? frame.y(share)", renderer)

    def test_media_history_methodology_is_in_header_info_control(self):
        media_section = self._section_html("media", "agenda")
        methodology = (
            "Part quotidienne des articles du périmètre « élection + campagne » "
            "associés à Marine Le Pen. La série couvre 29 jours UTC complets et "
            "ne mesure ni soutien, ni approbation, ni sentiment, ni intention de vote."
        )
        self.assertIn("candidate-media-history-panel", media_section)
        self.assertIn("candidate-media-history-chart", media_section)
        self.assertIn('aria-describedby="media-history-note"', media_section)
        self.assertIn(methodology, media_section)
        self.assertNotIn(
            f'<p class="candidate-method-note">{methodology}</p>',
            media_section,
        )
        self.assertNotIn(
            '<p class="candidate-method-note">Part quotidienne des articles du '
            'périmètre élection + campagne associés à la candidate.</p>',
            media_section,
        )

    def test_agenda_has_two_static_profile_cards_without_period_controls(self):
        agenda = self.published["agenda"]
        section = self._section_html("agenda", "scrutiny")
        current_card = self._agenda_profile_html(section, "current")
        cumulative_card = self._agenda_profile_html(section, "cumulative")
        self.assertEqual(section.count("<h3>PROFIL THÉMATIQUE · 30 J</h3>"), 1)
        self.assertEqual(
            section.count("<h3>PROFIL THÉMATIQUE · DEPUIS LE DÉBUT</h3>"), 1
        )
        self.assertEqual(section.count("<h3>ÉVOLUTION DES THÈMES</h3>"), 1)
        self.assertLess(section.index(current_card), section.index(cumulative_card))
        self.assertLess(
            section.index(cumulative_card), section.index("<h3>ÉVOLUTION DES THÈMES</h3>")
        )
        self.assertIn(
            f'{self._fr_count(agenda["current"]["association_count"], "association", "associations")} · '
            f'{self._fr_count(agenda["current"]["day_count"], "jour", "jours")}',
            current_card,
        )
        self.assertIn(
            f'{self._fr_count(agenda["since_tracking"]["association_count"], "association", "associations")} · '
            f'{self._fr_count(agenda["since_tracking"]["day_count"], "jour", "jours")}',
            cumulative_card,
        )
        for obsolete in (
            "candidate-agenda-period-switch",
            "data-agenda-period",
            "initAgendaProfile",
            ">30 J<",
            ">DEPUIS LE DÉBUT<",
        ):
            self.assertNotIn(obsolete, section)
            self.assertNotIn(obsolete, self.javascript)
        self.assertNotIn("aria-pressed", section)

    def test_agenda_profile_cards_share_topic_order_and_use_projected_shares(self):
        agenda = self.published["agenda"]
        section = self._section_html("agenda", "scrutiny")
        cards = {
            "current": self._agenda_profile_html(section, "current"),
            "cumulative": self._agenda_profile_html(section, "cumulative"),
        }
        expected_order = [
            topic["id"]
            for topic in sorted(
                agenda["current"]["topics"],
                key=lambda item: (-item["share"], item["id"]),
            )
        ]
        for card in cards.values():
            self.assertEqual(
                re.findall(r'data-topic-id="([^"]+)"', card), expected_order
            )
            self.assertEqual(card.count('class="candidate-topic-row"'), 8)

        for profile_name, card in cards.items():
            profile = agenda[
                "current" if profile_name == "current" else "since_tracking"
            ]
            topics_by_id = {topic["id"]: topic for topic in profile["topics"]}
            for topic_id in expected_order:
                topic = topics_by_id[topic_id]
                row = re.search(
                    rf'<li class="candidate-topic-row"[^>]*data-topic-id="{topic_id}"'
                    rf'[^>]*>(?P<body>.*?)</li>',
                    card,
                    flags=re.DOTALL,
                )
                self.assertIsNotNone(row)
                body = row.group("body")
                self.assertIn(
                    f'<strong>{reference._percent(topic["share"])}</strong>', body
                )
                self.assertIn(
                    f'class="candidate-topic-bar" '
                    f'style="--topic-share:{topic["share"]}"',
                    body,
                )
                self.assertNotIn(
                    f'<strong>{reference._number(topic["count"])}</strong>', body
                )
            zero_topics = [topic for topic in profile["topics"] if topic["share"] == 0]
            self.assertGreater(len(zero_topics), 0)
            for topic in zero_topics:
                self.assertIn(reference.TOPIC_LABELS_FR[topic["id"]], card)
                self.assertIn("0,0%", card)

    def test_agenda_profile_counts_remain_accessible_supporting_evidence(self):
        agenda = self.published["agenda"]
        section = self._section_html("agenda", "scrutiny")
        profiles = (
            (
                "current",
                agenda["current"],
                f'{agenda["current"]["day_count"]} derniers jours',
            ),
            ("cumulative", agenda["since_tracking"], "depuis le début du suivi"),
        )
        for modifier, profile, period_label in profiles:
            card = self._agenda_profile_html(section, modifier)
            for topic in profile["topics"]:
                row = re.search(
                    rf'<li class="candidate-topic-row" tabindex="0" '
                    rf'data-topic-id="{topic["id"]}" '
                    rf'aria-describedby="agenda-topic-{modifier}-{topic["id"]}-note" '
                    rf'aria-label="(?P<label>[^"]+)">(?P<body>.*?)</li>',
                    card,
                    flags=re.DOTALL,
                )
                self.assertIsNotNone(row)
                association_count = self._fr_count(
                    topic["count"], "association", "associations"
                )
                self.assertIn(
                    f'Part du profil : {reference._percent(topic["share"])}',
                    row.group("label"),
                )
                self.assertIn(association_count, row.group("label"))
                self.assertIn(f'Période : {period_label}', row.group("label"))
                for evidence in (
                    f'Part du profil : {reference._percent(topic["share"])}',
                    f'Associations : {reference._number(topic["count"])}',
                    f'Période : {period_label}',
                    'class="candidate-chart-tooltip candidate-topic-tooltip"',
                ):
                    self.assertIn(evidence, row.group("body"))
        self.assertNotIn("1 associations", section)

    def test_agenda_evolution_history_and_interaction_contract(self):
        published = self.published["agenda"]
        projected = self.projection["agenda"]
        self.assertEqual(published["evolution_topic_ids"], projected["evolution_topic_ids"])
        self.assertEqual(published["evolution"], projected["evolution"])

        renderer_start = self.javascript.index("const renderAgendaHistory")
        next_boundary = re.search(r"\n  const [A-Za-z0-9_]+ = ", self.javascript[renderer_start + 1:])
        self.assertIsNotNone(next_boundary)
        renderer_end = renderer_start + 1 + next_boundary.start()
        renderer = self.javascript[renderer_start:renderer_end]
        for text in (
            "height: 210",
            "pathFor(points, frame.x, frame.y, point => point.counts[topicId])",
            "candidate-agenda-zero-baseline",
            "point.counts[topicId]",
            'tooltip.className = "candidate-chart-tooltip"',
            "formatDate(point.date)",
            'class: "candidate-chart-date-hit-target"',
            'trigger.addEventListener("pointerenter"',
            'trigger.addEventListener("pointerdown"',
            'trigger.addEventListener("focus"',
            'trigger.addEventListener("keydown"',
            'event.key === "Escape"',
        ):
            self.assertIn(text, renderer)
        self.assertIn("candidateText(", renderer)
        self.assertIn("no average, smoothing or interpolation", renderer.lower())
        self.assertIn("sans moyenne, lissage ni interpolation", renderer)

    def test_agenda_structure_removes_comparison_markers_and_keeps_evolution_once(self):
        section = self._section_html("agenda", "scrutiny")
        self.assertEqual(section.count('class="candidate-topic-row"'), 16)
        self.assertEqual(section.count("<h3>ÉVOLUTION DES THÈMES</h3>"), 1)
        self.assertEqual(section.count('data-chart="agenda-history"'), 1)
        self.assertIn("4 thèmes principaux", section)
        for obsolete in (
            "candidate-agenda-comparison-key",
            "candidate-topic-cumulative-marker",
            "candidate-topic-comparison-track",
        ):
            self.assertNotIn(obsolete, section)
            self.assertNotIn(obsolete, self.css)
        self.assertIn(
            "Ils décrivent la composition de la couverture médiatique, pas les "
            "priorités ou positions de la candidate.",
            section,
        )
        visible = html_module.unescape(re.sub(r"<[^>]+>", " ", section)).lower()
        self.assertNotIn("priorités du programme", visible)
        self.assertNotIn("priorités des électeurs", visible)
        self.assertNotIn("positions politiques déduites", visible)

    def _current_news_records(self):
        news = self.sources["news_wire"]
        period = news["candidate_visibility"]["current_period"]
        primary = set(news["candidate_visibility"]["primary_scopes"])
        return [
            item
            for item in news["candidate_watch"]
            if "Marine Le Pen" in item.get("candidates", [])
            and item.get("coverage_scope") in primary
            and period["start_date"] <= item["published_at"][:10] <= period["end_date"]
        ]

    def _section_html(self, section_id, next_section_id):
        match = re.search(
            rf'<section class="candidate-section[^"]*" id="{section_id}".*?'
            rf'(?=<section class="candidate-section[^"]*" id="{next_section_id}")',
            self.html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        return match.group(0)

    def _agenda_profile_html(self, section, modifier):
        match = re.search(
            rf'<article class="candidate-panel candidate-agenda-profile '
            rf'candidate-agenda-profile-{modifier}">(?P<body>.*?)</article>',
            section,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        return match.group(0)

    @staticmethod
    def _fr_count(count, singular, plural):
        return f"{reference._number(count)} {singular if count == 1 else plural}"

    def _actualite_card(self, class_name):
        section = self._section_html("now", "polling")
        match = re.search(
            rf'<article class="candidate-panel {class_name}">(?P<body>.*?)'
            rf'(?=<article class="candidate-panel |\s*</div>\s*</section>)',
            section,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        return match.group("body")

    def test_actualite_latest_articles_use_media_preview_order(self):
        projected = self.published["media"]["latest_coverage"]
        expected = projected[:5]
        card = self._actualite_card("candidate-latest-news")
        self.assertIn("<h3>DERNIÈRES ACTUALITÉS</h3>", card)
        self.assertIn(
            f'<span>{len(expected)} article{"" if len(expected) == 1 else "s"}</span>',
            card,
        )
        self.assertEqual(card.count('class="candidate-coverage-item"'), len(expected))
        positions = []
        for item in expected:
            escaped_headline = html_module.escape(item["headline"], quote=True)
            escaped_url = html_module.escape(item["url"], quote=True)
            self.assertIn(escaped_headline, card)
            self.assertIn(f'href="{escaped_url}"', card)
            positions.append(card.index(escaped_headline))
        self.assertEqual(positions, sorted(positions))
        if len(projected) > 5:
            sixth_headline = html_module.escape(projected[5]["headline"], quote=True)
            self.assertNotIn(sixth_headline, card)

    def test_actualite_events_prioritize_upcoming_then_recent(self):
        upcoming = self.published["events"]["upcoming"]
        recent = self.published["events"]["recent"]
        selected_upcoming = upcoming[:5]
        selected_recent = recent[: 5 - len(selected_upcoming)]
        expected = selected_upcoming + selected_recent
        card = self._actualite_card("candidate-actualite-events")
        self.assertIn("<h3>ÉVÉNEMENTS</h3>", card)
        self.assertLessEqual(len(expected), 5)
        self.assertEqual(card.count('class="candidate-event-item"'), len(expected))
        self.assertEqual((len(selected_upcoming), len(selected_recent)), (1, 4))
        self.assertIn("1 à venir · 4 récents", card)
        positions = []
        for item in expected:
            escaped_title = html_module.escape(item["title"], quote=True)
            self.assertIn(escaped_title, card)
            positions.append(card.index(escaped_title))
            source = item.get("source")
            if source:
                self.assertIn(
                    f'href="{html_module.escape(source["url"], quote=True)}"',
                    card,
                )
        self.assertEqual(positions, sorted(positions))

        full_events = self._section_html("events", "related-candidates")
        self.assertEqual(
            full_events.count('class="candidate-event-item"'),
            len(upcoming) + len(recent),
        )
        for item in upcoming + recent:
            self.assertIn(html_module.escape(item["title"], quote=True), full_events)

    def test_events_viewport_has_one_authoritative_geometry_contract(self):
        events_css = self.css[
            self.css.index("/* === EVENTS VIEWPORT CONTRACT START ==="):
            self.css.index("/* === EVENTS VIEWPORT CONTRACT END ===")
        ]
        events_js = self.javascript[
            self.javascript.index("// === EVENTS VIEWPORT CONTRACT START ==="):
            self.javascript.index("// === EVENTS VIEWPORT CONTRACT END ===")
        ]

        for contract in (
            "height: var(--candidate-events-visible-height);",
            "overflow-y: scroll;",
            "overflow-x: hidden;",
            "scrollbar-gutter: stable;",
            "scrollbar-width: thin;",
            "align-content: start;",
        ):
            self.assertIn(contract, events_css)

        self.assertEqual(
            self.javascript.count("const initCandidateEventsViewport"),
            1,
        )
        self.assertIn("const recentList = lists[1];", events_js)
        self.assertIn("const thirdRect = recentItems[2].getBoundingClientRect();", events_js)
        self.assertIn("recentList.scrollTop + paddingBottom", events_js)
        self.assertIn('document.fonts.ready.then(syncGeometry)', events_js)
        self.assertIn('window.addEventListener("resize", syncGeometry', events_js)
        self.assertNotIn("ResizeObserver", events_js)
        self.assertLess(
            self.javascript.index("// === EVENTS VIEWPORT CONTRACT START ==="),
            self.javascript.index("// === FR27 SCRUTINY SCROLL PATCH START ==="),
        )

        for obsolete in (
            "EVENTS EQUAL THREE-ROW VIEWPORT",
            "candidate-events-third-gap",
            "initCandidateEventViewport",
            "naturalSparseHeight",
            "threeRowHeights",
            "285px",
            "max-height: 360px",
        ):
            self.assertNotIn(obsolete, self.css + self.javascript)

        full_events = self._section_html("events", "related-candidates")
        self.assertNotIn("data-archive-toggle", full_events)
        self.assertNotIn("Afficher plus", full_events)
        self.assertNotIn("Show more", full_events)

    def test_actualite_changes_keep_all_projected_records(self):
        changes = self.published["now"]["recent_changes"]
        card = self._actualite_card("candidate-recent-changes")
        self.assertEqual(len(changes), 6)
        self.assertIn("<span>6 éléments</span>", card)
        self.assertEqual(card.count('class="candidate-ledger-item"'), len(changes))
        positions = []
        for item in changes:
            escaped_headline = html_module.escape(item["headline"], quote=True)
            self.assertIn(escaped_headline, card)
            positions.append(card.index(escaped_headline))
        self.assertEqual(positions, sorted(positions))

    def test_actualite_preserves_projection_contract_and_public_vocabulary(self):
        self.assertEqual(
            self.published["now"]["latest_development"],
            self.projection["now"]["latest_development"],
        )
        self.assertEqual(
            self.published["media"]["latest_coverage"],
            self.projection["media"]["latest_coverage"],
        )
        self.assertEqual(self.published["events"], self.projection["events"])
        section = self._section_html("now", "polling")
        self.assertIn(
            "Derniers articles, événements et changements sourcés.",
            section,
        )
        self.assertNotIn("DERNIER DÉVELOPPEMENT", section)
        self.assertNotIn("PROCHAIN ÉVÉNEMENT", section)
        self.assertNotIn("DERNIER ÉVÉNEMENT", section)

    def test_media_projection_uses_exact_published_29_day_history(self):
        history = self.published["media"]["recent_history"]
        source_candidate = next(
            item
            for item in self.sources["candidate_visibility_history"]["candidates"]
            if item["candidate_id"] == reference.CANDIDATE_ID
        )
        self.assertEqual(history, source_candidate["campaign_attention"]["daily_series"])
        self.assertEqual(len(history), 29)
        self.assertIn("29 jours complets · UTC", self.html)

    def test_wikipedia_attention_is_not_presented_as_opinion(self):
        warning = (
            "Les pages vues Wikipédia mesurent la consultation de l’article. "
            "Elles ne mesurent ni soutien, ni sentiment, ni approbation, ni intention de vote."
        )
        self.assertIn(warning, self.html)
        self.assertEqual(self.published["attention"]["evidence_state"], "observed")
        self.assertEqual(len(self.published["attention"]["daily_series"]), 90)

    def test_scrutiny_preserves_by_and_about(self):
        relationships = {
            review["relationship"]
            for review in self.published["accountability"]["reviews"]
        }
        self.assertEqual(relationships, {"by", "about"})
        self.assertIn(">PAR<", self.html)
        self.assertIn(">À PROPOS<", self.html)
        self.assertIn(
            "affirmation attribuée à Marine Le Pen",
            self.html,
        )
        self.assertIn(
            (
                "Marine Le Pen est mentionnée ; l’affirmation est "
                "attribuée à une autre personne"
            ),
            self.html,
        )

    def test_all_active_candidates_have_valid_projection_shapes(self):
        active = reference.active_candidate_records(
            self.sources["candidate_candidacy_status"]
        )

        original_validate_sources = reference.validate_sources
        reference.validate_sources = lambda *_args, **_kwargs: None

        try:
            projected = [
                reference.build_projection(
                    self.sources,
                    ROOT,
                    candidate_id=candidate["candidate_id"],
                )
                for candidate in active
            ]
        finally:
            reference.validate_sources = original_validate_sources

        self.assertEqual(len(projected), len(active))

        self.assertEqual(
            {payload["candidate_id"] for payload in projected},
            {candidate["candidate_id"] for candidate in active},
        )

        for payload in projected:
            reference.validate_projection(
                payload,
                candidate_id=payload["candidate_id"],
            )

            if (
                payload["polling"]["current"]["evidence_state"]
                == "not_observed"
            ):
                self.assertIsNone(
                    payload["polling"]["current"]["pollster"]
                )
                self.assertIsNone(
                    payload["polling"]["current"]["fieldwork_start"]
                )
                self.assertEqual(
                    payload["polling"]["current"]["source_urls"],
                    [],
                )

    def test_generic_candidate_identity_helpers_preserve_reference_and_fallbacks(self):
        self.assertEqual(
            reference._candidate_status_label_fr(
                "declared",
                reference_candidate=True,
            ),
            "DÉCLARÉE",
        )

        self.assertEqual(
            reference._candidate_status_label_fr(
                "declared",
            ),
            "CANDIDATURE DÉCLARÉE",
        )

        self.assertEqual(
            reference._candidate_status_label_fr(
                "active_potential",
            ),
            "CANDIDATURE POTENTIELLE",
        )

        fallback = reference._candidate_portrait_html(
            {
                "candidate_name": "Example Candidate",
                "portrait_path": None,
            }
        )

        self.assertIn(
            "candidate-portrait-fallback",
            fallback,
        )
        self.assertIn(">EC<", fallback)
        self.assertNotIn("<img", fallback)

        portrait = reference._candidate_portrait_html(
            {
                "candidate_name": "Marine Le Pen",
                "portrait_path": "/assets/candidates/lepen.png",
            }
        )

        self.assertIn(
            'src="/assets/candidates/lepen.png"',
            portrait,
        )
        self.assertIn(
            "Portrait illustré de Marine Le Pen",
            portrait,
        )

    def test_not_observed_poll_and_campaign_agenda_render_without_null_assumptions(self):
        original_validate_sources = reference.validate_sources
        reference.validate_sources = lambda *_args, **_kwargs: None

        try:
            bruno = reference.build_projection(
                self.sources,
                ROOT,
                candidate_id="bruno-le-maire",
            )

            self.assertEqual(
                bruno["polling"]["current"]["evidence_state"],
                "not_observed",
            )

            bruno_fr = reference.render_html(
                bruno,
                reference.derive_hud_metrics(self.sources),
                lang="fr",
            ).decode("utf-8")

            bruno_en = reference.render_html(
                bruno,
                reference.derive_hud_metrics(self.sources),
                lang="en",
            ).decode("utf-8")

            self.assertIn(
                "Non observé dans la dernière vague",
                bruno_fr,
            )

            self.assertIn(
                "Not observed in the latest wave",
                bruno_en,
            )

            nathalie = reference.build_projection(
                self.sources,
                ROOT,
                candidate_id="nathalie-arthaud",
            )

            topic_ids = {
                topic["id"]
                for topic in nathalie["agenda"]["current"]["topics"]
            }

            self.assertIn(
                "candidacies_endorsements",
                topic_ids,
            )

            self.assertEqual(
                reference._candidate_topic_label_fr(
                    {"id": "candidacies_endorsements"}
                ),
                "CANDIDATURES & SOUTIENS",
            )

            nathalie_fr = reference.render_html(
                nathalie,
                reference.derive_hud_metrics(self.sources),
                lang="fr",
            ).decode("utf-8")

            self.assertIn(
                "Aucune activité thématique observée",
                nathalie_fr,
            )

        finally:
            reference.validate_sources = original_validate_sources

    def test_not_observed_media_uses_explicit_empty_states_and_keeps_history(self):
        original_validate_sources = reference.validate_sources
        reference.validate_sources = lambda *_args, **_kwargs: None

        try:
            payload = reference.build_projection(
                self.sources,
                ROOT,
                candidate_id="nathalie-arthaud",
            )

            self.assertEqual(
                payload["media"]["summary"]["evidence_state"],
                "not_observed",
            )

            self.assertEqual(
                len(payload["media"]["recent_history"]),
                29,
            )

            hud = reference.derive_hud_metrics(
                self.sources
            )

            rendered_fr = reference.render_html(
                payload,
                hud,
                lang="fr",
            ).decode("utf-8")

            rendered_en = reference.render_html(
                payload,
                hud,
                lang="en",
            ).decode("utf-8")

            for phrase in (
                "Non observé dans la fenêtre courante",
                "Structure de couverture indisponible",
                "Aucun éditeur observé",
                "Aucun groupe narratif observé",
                "Aucune couverture récente",
            ):
                self.assertIn(
                    phrase,
                    rendered_fr,
                )

            for phrase in (
                "Not observed in the current window",
                "Coverage structure unavailable",
                "No publisher observed",
                "No story cluster observed",
                "No recent coverage",
            ):
                self.assertIn(
                    phrase,
                    rendered_en,
                )

            self.assertIn(
                'data-chart="media-history"',
                rendered_fr,
            )

            self.assertIn(
                'data-chart="media-history"',
                rendered_en,
            )

        finally:
            reference.validate_sources = original_validate_sources

    def test_unavailable_wikipedia_attention_uses_explicit_bilingual_empty_states(self):
        original_validate_sources = reference.validate_sources
        reference.validate_sources = lambda *_args, **_kwargs: None

        try:
            hud = reference.derive_hud_metrics(
                self.sources
            )

            unavailable = reference.build_projection(
                self.sources,
                ROOT,
                candidate_id="benoit-mathieu",
            )

            self.assertEqual(
                unavailable["attention"]["evidence_state"],
                "unavailable_no_personal_article",
            )

            self.assertIsNone(
                unavailable["attention"]["wikipedia_article"],
            )

            self.assertEqual(
                unavailable["attention"]["daily_series"],
                [],
            )

            rendered_fr = reference.render_html(
                unavailable,
                hud,
                lang="fr",
            ).decode("utf-8")

            rendered_en = reference.render_html(
                unavailable,
                hud,
                lang="en",
            ).decode("utf-8")

            for phrase in (
                "Attention Wikipédia indisponible",
                "Historique indisponible",
                "aucune série",
            ):
                self.assertIn(
                    phrase,
                    rendered_fr,
                )

            for phrase in (
                "Wikipedia attention unavailable",
                "History unavailable",
                "no series",
            ):
                self.assertIn(
                    phrase,
                    rendered_en,
                )

            self.assertNotIn(
                'data-chart="attention-history"',
                rendered_fr,
            )

            self.assertNotIn(
                'data-chart="attention-history"',
                rendered_en,
            )

            observed = reference.build_projection(
                self.sources,
                ROOT,
                candidate_id="marine-le-pen",
            )

            observed_fr = reference.render_html(
                observed,
                hud,
                lang="fr",
            ).decode("utf-8")

            observed_en = reference.render_html(
                observed,
                hud,
                lang="en",
            ).decode("utf-8")

            self.assertIn(
                'data-chart="attention-history"',
                observed_fr,
            )

            self.assertIn(
                'data-chart="attention-history"',
                observed_en,
            )

            self.assertIn(
                "Ouvrir l’article Wikipédia",
                observed_fr,
            )

            self.assertIn(
                "Open Wikipedia article",
                observed_en,
            )

        finally:
            reference.validate_sources = original_validate_sources

    def test_zero_evidence_sections_use_bilingual_empty_states_without_empty_charts(self):
        original_validate_sources = reference.validate_sources
        reference.validate_sources = lambda *_args, **_kwargs: None

        try:
            hud = reference.derive_hud_metrics(self.sources)
            sparse = reference.build_projection(
                self.sources,
                ROOT,
                candidate_id="benoit-mathieu",
            )
            sparse_fr = reference.render_html(
                sparse,
                hud,
                lang="fr",
            ).decode("utf-8")
            sparse_en = reference.render_html(
                sparse,
                hud,
                lang="en",
            ).decode("utf-8")

            for phrase in (
                "Aucun historique de premier tour observé",
                "Aucun duel de second tour observé",
                "Aucune activité thématique observée",
                "Historique thématique indisponible",
                "Aucune vérification associée",
                "Aucun événement publié",
            ):
                self.assertIn(phrase, sparse_fr)

            for phrase in (
                "No first-round history observed",
                "No runoff observed",
                "No thematic activity observed",
                "Thematic history unavailable",
                "No associated review",
                "No published events",
            ):
                self.assertIn(phrase, sparse_en)

            for document in (sparse_fr, sparse_en):
                self.assertNotIn('data-chart="poll-history"', document)
                self.assertNotIn('data-chart="agenda-history"', document)
                self.assertNotIn(">None<", document)
                self.assertNotIn(">null<", document)

            historical = reference.build_projection(
                self.sources,
                ROOT,
                candidate_id="francis-lalanne",
            )
            historical_fr = reference.render_html(
                historical,
                hud,
                lang="fr",
            ).decode("utf-8")

            self.assertEqual(
                historical["agenda"]["current"]["association_count"],
                0,
            )
            self.assertGreater(
                historical["agenda"]["since_tracking"]["association_count"],
                0,
            )
            self.assertIn(
                "Aucune activité thématique observée",
                historical_fr,
            )
            self.assertIn('data-chart="agenda-history"', historical_fr)

        finally:
            reference.validate_sources = original_validate_sources

    def test_related_profiles_use_declared_candidacy_rotation(self):
        page_index = reference.project_candidate_page_index(
            self.sources["candidate_candidacy_status"]
        )

        ordered = page_index["candidates"]

        current_index = next(
            index
            for index, item in enumerate(ordered)
            if item["candidate_id"] == "marine-le-pen"
        )

        rotated = (
            ordered[current_index + 1:]
            + ordered[:current_index]
        )

        expected = [
            item["candidate_id"]
            for item in rotated
            if item["status"] == "declared"
        ][:8]

        actual = [
            item["candidate_id"]
            for item in self.projection["related_candidates"]
        ]

        self.assertEqual(actual, expected)
        self.assertLessEqual(len(actual), 8)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertNotIn("marine-le-pen", actual)

        self.assertTrue(
            all(
                item["status"] == "declared"
                for item in self.projection["related_candidates"]
            )
        )

        hud = reference.derive_hud_metrics(self.sources)

        rendered_fr = reference.render_html(
            self.projection,
            hud,
            lang="fr",
        ).decode("utf-8")

        rendered_en = reference.render_html(
            self.projection,
            hud,
            lang="en",
        ).decode("utf-8")

        self.assertIn(
            "POURSUIVRE L’EXPLORATION",
            rendered_fr,
        )

        self.assertIn(
            (
                '<h2 id="related-candidates-title">'
                "AUTRES CANDIDATURES DÉCLARÉES"
                "</h2>"
            ),
            rendered_fr,
        )

        self.assertIn(
            (
                '<h2 id="related-candidates-title">'
                "OTHER DECLARED CANDIDATES"
                "</h2>"
            ),
            rendered_en,
        )

        self.assertIn(
            'href="/candidates/">'
            "VOIR TOUS LES CANDIDATS →",
            rendered_fr,
        )

        self.assertIn(
            'href="/en/candidates/">'
            "VIEW ALL CANDIDATES →",
            rendered_en,
        )

        self.assertNotIn(
            "candidate-related-status",
            rendered_fr,
        )

        for item in self.projection["related_candidates"]:
            candidate_id = item["candidate_id"]

            self.assertIn(
                f'href="/candidates/{candidate_id}/"',
                rendered_fr,
            )

            self.assertIn(
                f'href="/en/candidates/{candidate_id}/"',
                rendered_en,
            )

        non_declared = reference.build_projection(
            self.sources,
            ROOT,
            candidate_id="marine-tondelier",
        )

        self.assertNotEqual(
            non_declared["candidate"]["status"],
            "declared",
        )

        self.assertTrue(
            all(
                item["status"] == "declared"
                for item in non_declared["related_candidates"]
            )
        )

        non_declared_fr = reference.render_html(
            non_declared,
            hud,
            lang="fr",
        ).decode("utf-8")

        non_declared_en = reference.render_html(
            non_declared,
            hud,
            lang="en",
        ).decode("utf-8")

        self.assertIn(
            (
                '<h2 id="related-candidates-title">'
                "CANDIDATURES DÉCLARÉES"
                "</h2>"
            ),
            non_declared_fr,
        )

        self.assertIn(
            (
                '<h2 id="related-candidates-title">'
                "DECLARED CANDIDATES"
                "</h2>"
            ),
            non_declared_en,
        )

        self.assertNotIn(
            'id="sources"',
            rendered_fr,
        )

        self.assertNotIn(
            'id="sources"',
            rendered_en,
        )

        self.assertIn(
            'id="related-candidates"',
            rendered_fr,
        )

        self.assertIn(
            ".candidate-related-grid",
            self.css,
        )

    def test_projection_is_bounded(self):
        payload = self.published
        bounds = payload["bounds"]
        self.assertLessEqual(len(payload["now"]["recent_changes"]), bounds["recent_changes"])
        self.assertLessEqual(len(payload["polling"]["tested_runoffs"]), bounds["runoff_matchups"])
        self.assertTrue(
            all(
                len(matchup["observations"]) <= bounds["runoff_events_per_matchup"]
                for matchup in payload["polling"]["tested_runoffs"]
            )
        )
        self.assertLessEqual(len(payload["media"]["top_publishers"]), bounds["top_publishers"])
        self.assertLessEqual(len(payload["media"]["top_story_clusters"]), bounds["story_clusters"])
        self.assertLessEqual(len(payload["media"]["latest_coverage"]), bounds["latest_coverage"])
        self.assertLessEqual(len(payload["accountability"]["reviews"]), bounds["scrutiny_reviews"])
        self.assertLess(DATA_PATH.stat().st_size, 150_000)

    def test_browser_has_no_runtime_news_wire_dependency(self):
        browser_sources = self.html + self.javascript + self.css + self.shell_css
        self.assertNotIn("news_wire.json", browser_sources)
        self.assertNotIn("polls.json", browser_sources)
        self.assertNotIn("candidate_signals.json", browser_sources)
        self.assertIn('"data_url":"/candidates/marine-le-pen/data.json"', self.html)

    def test_semantic_html_contains_frozen_structure_without_javascript(self):
        expected_order = [
            'class="candidate-masthead"',
            'class="candidate-breadcrumb"',
            'class="candidate-dossier"',
            'class="candidate-local-nav"',
            'id="now"',
            'id="polling"',
            'id="media"',
            'id="agenda"',
            'id="scrutiny"',
            'id="attention"',
            'id="events"',
            'id="related-candidates"',
            'id="candidate-app-hud"',
        ]
        offsets = [self.html.index(token) for token in expected_order]
        self.assertEqual(offsets, sorted(offsets))
        for text in (
            "Marine Le Pen",
            "DÉCLARÉE",
            "DERNIÈRES ACTUALITÉS",
            "DERNIÈRE VAGUE",
            "MEDIA PULSE",
            "STATUT DE CANDIDATURE",
            "POURSUIVRE L’EXPLORATION",
            "AUTRES CANDIDATURES DÉCLARÉES",
        ):
            self.assertIn(text, self.html)
        self.assertIn("<h1 id=\"candidate-name\">Marine Le Pen</h1>", self.html)

    def test_dossier_description_is_an_accessible_localized_name_tooltip(self):
        note_fr = (
            "Synthèse descriptive des données publiées par France 2027 Signal Lab. "
            "Aucune moyenne · aucune prévision · aucun conseil de vote."
        )
        note_en = (
            "Descriptive summary of data published by France 2027 Signal Lab. "
            "No average · no forecast · no voting advice."
        )
        rendered_en = reference.render_html(
            self.projection,
            reference.derive_hud_metrics(self.sources),
            lang="en",
        ).decode("utf-8")

        for document, note, label in (
            (self.html, note_fr, "Informations sur ce dossier"),
            (rendered_en, note_en, "Information about this dossier"),
        ):
            self.assertIn('<div class="candidate-name-row">', document)
            self.assertIn('<h1 id="candidate-name">Marine Le Pen</h1>', document)
            self.assertIn(
                f'aria-label="{label}" aria-describedby="candidate-dossier-note"',
                document,
            )
            self.assertIn(
                '<span class="candidate-section-tooltip" '
                'id="candidate-dossier-note" role="tooltip">'
                + note
                + "</span>",
                document,
            )
            self.assertNotIn(f"<p>{note}</p>", document)

        self.assertNotIn(".candidate-dossier-copy > p", self.css)

    def test_candidate_application_hud_structure_and_static_metrics(self):
        self.assertNotIn('class="candidate-footer"', self.html)
        self.assertEqual(self.html.count('id="candidate-app-hud"'), 1)
        self.assertEqual(self.html.count('class="fr27-app-hud"'), 1)

        metrics = reference.derive_hud_metrics(self.sources)
        self.assertIn(
            f'id="fr27-hud-domains-value">{metrics["domains"]}</strong>',
            self.html,
        )
        self.assertIn(
            f'id="fr27-hud-polls-value">{metrics["poll_packages"]}</strong>',
            self.html,
        )
        self.assertNotIn("fr27-hud-metric-loading", self.html)

        for token in (
            'id="fr27-hud-paris-zone"',
            'id="fr27-hud-paris-time"',
            'id="fr27-hud-paris-date"',
            'id="fr27-hud-countdown-days"',
            'datetime="2027-04-18"',
            'id="fr27-hud-domains-value"',
            'id="fr27-hud-polls-value"',
            'href="https://france2027.app/"',
            '>TABLEAU DE BORD<',
            '>OUVRIR LE MONITEUR ↗<',
            'class="fr27-hud-command github"',
            'id="fr27-hud-email-toggle"',
            'id="fr27-hud-share"',
            'id="fr27-hud-info-toggle"',
            'id="fr27-app-hud-toggle"',
            'data-expanded="true"',
            'aria-expanded="true"',
            'aria-controls="fr27-app-hud-surface"',
            'aria-hidden="false"',
        ):
            self.assertIn(token, self.html)

    def test_hud_metrics_follow_dashboard_contracts_without_projection_changes(self):
        manifest_value = self.sources["publication_manifest"]["source_network"][
            "approved_publisher_domains"
        ]
        expected_packages = {
            (
                event["pollster"],
                event["fieldwork_start"],
                event["fieldwork_end"],
                event["sample_size"],
            )
            for event in self.sources["polls"]
            if event["round"] == "first_round"
        }
        metrics = reference.derive_hud_metrics(self.sources)
        self.assertEqual(metrics["domains"], manifest_value)
        self.assertEqual(metrics["poll_packages"], len(expected_packages))
        self.assertNotIn("hud", self.published)

    def test_hud_controller_preserves_production_interaction_contract(self):
        controller = self.javascript[
            self.javascript.index("// FR27 APPLICATION HUD CONTROLLER") :
            self.javascript.index("const loadProjection")
        ]
        for token in (
            'toggle.addEventListener("click"',
            'event.key !== "Escape"',
            "syncHudGeometry",
            "getBoundingClientRect",
            'window.addEventListener("resize"',
            '"ResizeObserver" in window',
            'new ResizeObserver(syncHudGeometry)',
            'timeZone: "Europe/Paris"',
            "refreshParisClock",
            'content.setAttribute("aria-hidden"',
            '"inert" in content',
            "fr27-app-hud-collapsed",
        ):
            self.assertIn(token, controller)
        self.assertIn("refreshCountdown", self.javascript)
        self.assertNotIn("fr27-hud-domains-value", controller)
        self.assertNotIn("fr27-hud-polls-value", controller)

    def test_hud_css_is_namespaced_and_legacy_footer_rules_are_removed(self):
        combined = self.css + self.shell_css
        self.assertIn("FR27 APPLICATION HUD — CANDIDATE-PAGE TRANSPLANT", self.css)
        self.assertIn(".candidate-page #candidate-app-hud.fr27-app-hud", self.css)
        self.assertNotIn(".candidate-footer", combined)

    def test_public_vocabulary_excludes_internal_prototype_terms(self):
        prohibited = (
            "DOSSIER CANDIDATE",
            "ÉVIDENCE SONDAGE",
            "ÉVIDENCE ACTUELLE",
            "RESPONSABILITÉ",
            "PREUVE DE CANDIDATURE",
            "Ouvrir la preuve",
            "FRAÎCHEUR DES PREUVES",
            "PROCHAIN / RÉCENT ÉVÉNEMENT",
            "CHANGEMENTS RÉCENTS",
            "archive bornée",
            "archives bornées",
            "paquet de sondage",
            "identifiant canonique",
            "data.json",
            "News Wire",
            "Projection fixe",
            "Projection candidate",
        )
        for term in prohibited:
            self.assertNotIn(term, self.visible_text)

    def test_mobile_local_navigation_selector_is_progressive_enhancement(self):
        root = Path(__file__).resolve().parent
        css = (root / "assets" / "candidate-page.css").read_text(
            encoding="utf-8"
        )
        js = (root / "assets" / "candidate-page.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("candidate-local-nav-mobile", css)
        self.assertIn(
            "@media (max-width: 759.98px)",
            css,
        )
        self.assertIn(
            ".candidate-local-nav.has-mobile-selector > a",
            css,
        )

        self.assertIn(
            'mobileControl.className = "candidate-local-nav-mobile"',
            js,
        )
        self.assertIn(
            'mobileSelect.className = "candidate-local-nav-mobile-select"',
            js,
        )
        self.assertIn(
            'mobileSelect.value = activeHref',
            js,
        )
        self.assertIn(
            'nav.classList.add("has-mobile-selector")',
            js,
        )

    def test_javascript_only_enhances_existing_html(self):
        self.assertNotIn("document.body.innerHTML", self.javascript)
        self.assertNotIn("document.documentElement.innerHTML", self.javascript)
        self.assertIn("renderCharts(await loadProjection())", self.javascript)
        self.assertIn("semantic HTML remains active", self.javascript)

    def test_css_has_one_namespace_and_three_geometry_regimes(self):
        selector_lines = [
            line.strip()
            for line in (self.css + self.shell_css).splitlines()
            if line.strip().endswith("{") and not line.lstrip().startswith("@")
        ]
        self.assertTrue(selector_lines)
        for line in selector_lines:
            self.assertTrue(
                line.startswith(".candidate-page") or line.startswith("from") or line.startswith("to"),
                line,
            )
        self.assertIn("@media (min-width: 760px) and (max-width: 1349.98px)", self.css)
        self.assertIn("@media (max-width: 759.98px)", self.css)
        self.assertIn("grid-template-columns: minmax(280px, 32fr) minmax(0, 68fr)", self.css)
        self.assertIn("grid-template-columns: minmax(0, 65fr) minmax(300px, 35fr)", self.css)
        self.assertIn("position: sticky", self.css)
        self.assertIn("scroll-margin-top", self.css)




class CandidateBilingualReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import re

        cls.re = re
        cls.sources = reference.load_sources(ROOT)
        reference.validate_sources(cls.sources, ROOT)
        cls.projection = reference.build_projection(cls.sources, ROOT)
        cls.hud_metrics = reference.derive_hud_metrics(cls.sources)

        cls.fr = reference.render_html(
            cls.projection,
            cls.hud_metrics,
            lang="fr",
        ).decode("utf-8")
        cls.en = reference.render_html(
            cls.projection,
            cls.hud_metrics,
            lang="en",
        ).decode("utf-8")

    def test_both_language_outputs_are_generated(self):
        self.assertTrue(
            (ROOT / "candidates" / "marine-le-pen" / "index.html").exists()
        )
        self.assertTrue(
            (ROOT / "en" / "candidates" / "marine-le-pen" / "index.html").exists()
        )

    def test_events_structure_order_counts_and_sources_are_bilingual_peers(self):
        def section(document):
            match = self.re.search(
                r'<section class="candidate-section" id="events".*?'
                r'(?=<section class="candidate-section candidate-related")',
                document,
                flags=self.re.DOTALL,
            )
            self.assertIsNotNone(match)
            return match.group(0)

        def event_contract(document):
            result = []
            for item in self.re.findall(
                r'<article class="candidate-event-item">.*?</article>',
                section(document),
                flags=self.re.DOTALL,
            ):
                result.append(
                    (
                        self.re.search(r'<time datetime="([^"]+)"', item).group(1),
                        self.re.search(r'<h4(?: lang="fr")?>(.*?)</h4>', item).group(1),
                        self.re.search(r'<a class="candidate-source-link" href="([^"]+)"', item).group(1),
                    )
                )
            return result

        fr_events = section(self.fr)
        en_events = section(self.en)
        self.assertEqual(
            self.re.findall(r'<(/?)([a-z0-9]+)(?:\s+[^>]*)?>', fr_events),
            self.re.findall(r'<(/?)([a-z0-9]+)(?:\s+[^>]*)?>', en_events),
        )
        self.assertEqual(
            self.re.findall(r'class="([^"]+)"', fr_events),
            self.re.findall(r'class="([^"]+)"', en_events),
        )
        self.assertEqual(event_contract(self.fr), event_contract(self.en))
        self.assertEqual(
            fr_events.count('class="candidate-panel-body candidate-event-list"'),
            2,
        )
        self.assertEqual(
            en_events.count('class="candidate-panel-body candidate-event-list"'),
            2,
        )
        self.assertEqual(
            fr_events.count('class="candidate-event-item"'),
            len(self.projection["events"]["upcoming"])
            + len(self.projection["events"]["recent"]),
        )
        for document in (fr_events, en_events):
            self.assertNotIn("data-archive-toggle", document)
            self.assertNotIn("Afficher plus", document)
            self.assertNotIn("Show more", document)

    def test_document_language_contract(self):
        self.assertIn('<html lang="fr"', self.fr)
        self.assertIn('<html lang="en"', self.en)

    def test_canonical_and_reciprocal_hreflang_contract(self):
        self.assertIn(
            '<link rel="canonical" href="https://france2027.app/candidates/marine-le-pen/">',
            self.fr,
        )
        self.assertIn(
            '<link rel="canonical" href="https://france2027.app/en/candidates/marine-le-pen/">',
            self.en,
        )

        for document in (self.fr, self.en):
            self.assertIn(
                'hreflang="fr" href="https://france2027.app/candidates/marine-le-pen/"',
                document,
            )
            self.assertIn(
                'hreflang="en" href="https://france2027.app/en/candidates/marine-le-pen/"',
                document,
            )
            self.assertIn(
                'hreflang="x-default" href="https://france2027.app/candidates/marine-le-pen/"',
                document,
            )

    def test_language_toggle_opens_candidate_peer_at_top(self):
        self.assertIn(
            'data-candidate-peer-base="/en/candidates/marine-le-pen/"',
            self.fr,
        )
        self.assertIn(
            'data-candidate-peer-base="/candidates/marine-le-pen/"',
            self.en,
        )
        self.assertIn('aria-current="page">FR</a>', self.fr)
        self.assertIn('aria-current="page">EN</a>', self.en)

        javascript = Path("assets/candidate-page.js").read_text(
            encoding="utf-8"
        )

        start = javascript.index(
            "const initCandidateLanguageToggle"
        )
        end = javascript.index(
            "const init = async",
            start,
        )
        toggle = javascript[start:end]

        self.assertIn(
            'peer.setAttribute("href", base);',
            toggle,
        )
        self.assertNotIn(
            "window.location.hash",
            toggle,
        )
        self.assertNotIn(
            "${base}${hash}",
            toggle,
        )

    def test_nested_english_route_preserves_candidate_images_and_brand_mark(self):
        import re

        for document in (self.fr, self.en):
            self.assertNotIn(
                "../../assets/candidates/",
                document,
            )

            for portrait in (
                "philippe.png",
                "melenchon.png",
                "attal.png",
                "glucksmann.png",
                "hollande.png",
                "retailleau.png",
                "ruffin.png",
            ):
                self.assertIn(
                    f'/assets/candidates/{portrait}',
                    document,
                )

        mark_pattern = re.compile(
            r'<span class="candidate-mark".*?</span>',
            flags=re.DOTALL,
        )

        french_mark = mark_pattern.search(self.fr)
        english_mark = mark_pattern.search(self.en)

        self.assertIsNotNone(french_mark)
        self.assertIsNotNone(english_mark)

        self.assertEqual(
            french_mark.group(0),
            english_mark.group(0),
        )

        self.assertIn(
            'viewBox="0 0 32 32"',
            english_mark.group(0),
        )

        self.assertNotIn(
            'viewbox="0 0 32 32"',
            english_mark.group(0),
        )

        self.assertIn(
            'fill="#071522"/>',
            english_mark.group(0),
        )

    def test_candidate_slug_and_shared_data_contract_are_identical(self):
        for document in (self.fr, self.en):
            self.assertIn('data-page-candidate-id="marine-le-pen"', document)
            self.assertIn(
                '"data_url":"/candidates/marine-le-pen/data.json"',
                document,
            )

        self.assertFalse(
            (ROOT / "en" / "candidates" / "marine-le-pen" / "data.json").exists()
        )

    def test_both_languages_use_identical_shared_assets(self):
        shared = (
            "/assets/fr27-ui.css",
            "/assets/candidate-page-shell.css",
            "/assets/candidate-page.css",
            "/assets/fr27-ui.js",
            "/assets/candidate-page.js",
        )

        for asset in shared:
            self.assertIn(asset, self.fr)
            self.assertIn(asset, self.en)

        self.assertNotIn("candidate-page-en.css", self.en)
        self.assertNotIn("candidate-page-en.js", self.en)

    def test_english_generated_compositional_ui_is_localized(self):
        expected = (
            "33–36% · 5 hypotheses",
            "Harris · fieldwork from 8 Sep 2026 to 10 Sep 2026",
            "in the current 7-day window",
            "1 upcoming · 4 recent",
            "Period: last 30 days",
            "Period: since tracking began",
            "Profile share: 41.9%",
            "Associations: 18",
            "44 associations · 51 days",
            "FR27 on X · @fr27signal",
            "Economy and public finances. Profile share: 41.9%. "
            "18 associations. Period: last 30 days.",
            "Economy and public finances. Profile share: 43.2%. "
            "19 associations. Period: since tracking began.",
            "28.1%",
        )

        for value in expected:
            self.assertIn(value, self.en)

        forbidden = (
            "5 hypothèses",
            "terrain du",
            "sur la fenêtre courante de 7 jours",
            "1 à venir · 4 récents",
            "Période : 30 derniers jours",
            "Période : depuis le début du suivi",
            "Part du profil :",
            "Associations :",
            "44 associations · 51 jours",
            "FR27 sur X · @fr27signal",
            "28,1%",
        )

        for value in forbidden:
            self.assertNotIn(value, self.en)

        # Source-language evidence and scrutiny vocabulary intentionally remain French.
        self.assertIn(
            "Présidentielle 2027 : pour sa rentrée politique",
            self.en,
        )
        self.assertIn("Afficher plus de vérifications", self.en)

    def test_english_route_has_no_remaining_compositional_locale_leaks(self):
        expected = (
            "Harris · fieldwork from 8 Sep 2026 to 10 Sep 2026",
            '<span class="candidate-countdown-unit">days</span>',
            "CAMPAIGN · actu.fr",
            "ELECTION · Franceinfo Politique",
            "Enable JavaScript for the interactive visualization.",
            "7-day peak",
            "period peak",
            "Daily pageviews of Marine Le Pen&#x27;s French Wikipedia article",
            'title="French candidate page"',
            'aria-label="Utility links"',
            "27 articles · 21.8%",
            "3 articles · 1 publisher",
        )

        for value in expected:
            self.assertIn(value, self.en)

        forbidden = (
            "fieldwork from 8 sept. 2026",
            '<span class="candidate-countdown-unit">jours</span>',
            "CAMPAGNE · actu.fr",
            "ÉLECTION · Franceinfo Politique",
            "Activez JavaScript pour la visualisation interactive.",
            ">pic sur 7 jours<",
            ">pic de période<",
            'title="Page candidat en français"',
            'aria-label="Liens utilitaires"',
            "27 articles · 21,8%",
            "3 articles · 1 publishers",
        )

        for value in forbidden:
            self.assertNotIn(value, self.en)

    def test_intentionally_french_scrutiny_control_is_language_tagged(self):
        self.assertIn(
            '<button class="candidate-archive-toggle" type="button" lang="fr" '
            'data-archive-toggle aria-expanded="false">'
            'Afficher plus de vérifications</button>',
            self.en,
        )

    def test_english_runoff_interface_copy_is_localized(self):
        expected_english = (
            "7 opponents · 17 observations shown",
            "17 tests total · 3 most recent shown",
            "13 tests total · 3 most recent shown",
            "14 tests total · 3 most recent shown",
            "4 tests total · 3 most recent shown",
            "1 test total",
            "3 tests total",
            "Sample: 1,001",
            "Sample: 2,052",
        )

        for value in expected_english:
            self.assertIn(value, self.en)

        forbidden_english = (
            "7 adversaires · 17 observations affichées",
            "17 tests au total · 3 plus récents affichés",
            "13 tests au total · 3 plus récents affichés",
            "14 tests au total · 3 plus récents affichés",
            "4 tests au total · 3 plus récents affichés",
            "1 test au total",
            "3 tests au total",
            "Échantillon : 1,001",
            "Échantillon : 2,052",
        )

        for value in forbidden_english:
            self.assertNotIn(value, self.en)

        self.assertIn(
            "7 adversaires · 17 observations affichées",
            self.fr,
        )
        self.assertIn(
            "17 tests au total · 3 plus récents affichés",
            self.fr,
        )
        self.assertIn(
            "Échantillon : 1\u202f001",
            self.fr,
        )

    def test_english_page_has_no_known_product_ui_leaks(self):
        expected_english = (
            "before the first round",
            (
                "Descriptive summary of data published by France 2027 Signal Lab. "
                "No average · no forecast · no voting advice."
            ),
            "POLLING DATA",
            (
                "share of election + campaign coverage, "
                "not a measure of support"
            ),
            "articles · 7 active days",
            "<span>publishers</span>",
            "<span>story clusters</span>",
            "<span>active days</span>",
            "RECENT COVERAGE TREND",
            "Published history from 21 Aug 2026 to 18 Sep 2026.",
            (
                'aria-label="History of Marine Le Pen&#x27;s '
                'published first-round scores"'
            ),
            (
                'aria-label="Recent history of Marine Le Pen&#x27;s '
                'daily coverage share"'
            ),
            'data-collapsed-label="Show more reviews"',
        )

        for value in expected_english:
            self.assertIn(value, self.en)

        forbidden_english = (
            ">avant le premier tour<",
            "Synthèse descriptive des données publiées par France 2027 Signal Lab.",
            ">DONNÉES DE SONDAGE<",
            "part de la couverture élection + campagne, pas un indicateur de soutien",
            "articles · 7 jours actifs",
            "<span>éditeurs</span>",
            "<span>groupes narratifs</span>",
            "<span>jours actifs</span>",
            ">TENDANCE RÉCENTE DE COUVERTURE<",
            "Historique publié du 21 Aug 2026 au 18 Sep 2026.",
            (
                'aria-label="Historique des scores publiés '
                'au premier tour de Marine Le Pen"'
            ),
            (
                'aria-label="Historique récent de la part quotidienne '
                'de couverture de Marine Le Pen"'
            ),
            'data-collapsed-label="Afficher plus de vérifications"',
        )

        for value in forbidden_english:
            self.assertNotIn(value, self.en)

        french_contracts = (
            ">avant le premier tour<",
            "Synthèse descriptive des données publiées par France 2027 Signal Lab.",
            ">DONNÉES DE SONDAGE<",
            "articles · 7 jours actifs",
            "<span>éditeurs</span>",
            "<span>groupes narratifs</span>",
            "<span>jours actifs</span>",
            ">TENDANCE RÉCENTE DE COUVERTURE<",
            (
                'aria-label="Historique des scores publiés '
                'au premier tour de Marine Le Pen"'
            ),
            (
                'aria-label="Historique récent de la part quotidienne '
                'de couverture de Marine Le Pen"'
            ),
        )

        for value in french_contracts:
            self.assertIn(value, self.fr)

    def test_major_section_ids_are_stable_and_unique(self):
        expected = [
            "now",
            "polling",
            "media",
            "agenda",
            "scrutiny",
            "attention",
            "events",
            "related-candidates",
        ]

        def ids(document):
            return self.re.findall(
                r'<section class="candidate-section[^"]*" id="([^"]+)"',
                document,
            )

        self.assertEqual(ids(self.fr), expected)
        self.assertEqual(ids(self.en), expected)
        self.assertEqual(len(ids(self.fr)), len(set(ids(self.fr))))
        self.assertEqual(len(ids(self.en)), len(set(ids(self.en))))

    def test_structural_panel_and_evidence_counts_match(self):
        structural_tokens = (
            'class="candidate-panel',
            'class="candidate-runoff-card"',
            'class="candidate-runoff-group"',
            'class="candidate-coverage-item"',
            'class="candidate-topic-row"',
            'class="candidate-review-item"',
            'class="candidate-event-item"',
            'data-chart="poll-history"',
            'data-chart="media-history"',
            'data-chart="agenda-history"',
            'data-chart="attention-history"',
        )

        for token in structural_tokens:
            self.assertEqual(
                self.fr.count(token),
                self.en.count(token),
                token,
            )

    def test_external_evidence_urls_are_identical(self):
        pattern = self.re.compile(r'href="(https?://[^"]+)"')

        def evidence_urls(document):
            return sorted(
                url
                for url in pattern.findall(document)
                if "france2027.app/" not in url
            )

        self.assertEqual(
            evidence_urls(self.fr),
            evidence_urls(self.en),
        )

    def test_english_interface_vocabulary_is_present(self):
        expected = (
            "CANDIDATE DOSSIER",
            ">NEWS<",
            ">POLLS<",
            ">MEDIA<",
            "WHAT CHANGED",
            "MEDIA PULSE",
            "FIRST-ROUND HISTORY",
            "TESTED RUNOFFS",
            "TOP PUBLISHERS",
            "CLAIMS UNDER SCRUTINY",
            "CANDIDACY STATUS",
            "WIKIPEDIA PAGEVIEWS",
            "UPCOMING EVENTS",
            "CONTINUE EXPLORING",
            "OTHER DECLARED CANDIDATES",
            "VIEW ALL CANDIDATES →",
            "OPEN THE MONITOR",
        )

        for text in expected:
            self.assertIn(text, self.en)

    def test_known_french_interface_labels_do_not_leak_into_english(self):
        forbidden = (
            ">ACTUALITÉ<",
            ">SONDAGES<",
            ">MÉDIAS<",
            ">VÉRIFICATIONS<",
            ">ÉVÉNEMENTS<",
            ">DERNIÈRE VAGUE<",
            ">HISTORIQUE DU PREMIER TOUR<",
            ">STATUT DE CANDIDATURE<",
            ">FRAÎCHEUR DES DONNÉES<",
            ">COMPTE À REBOURS<",
            ">OUVRIR LE MONITEUR ↗<",
            'aria-label="Contexte de cette section"',
            "Informations sur l’historique",
        )

        for text in forbidden:
            self.assertNotIn(text, self.en)

    def test_french_reference_remains_french(self):
        expected = (
            ">ACTUALITÉ<",
            ">SONDAGES<",
            ">MÉDIAS<",
            ">VÉRIFICATIONS<",
            ">ÉVÉNEMENTS<",
            "DOSSIER CANDIDAT",
            "POURSUIVRE L’EXPLORATION",
            "AUTRES CANDIDATURES DÉCLARÉES",
            "VOIR TOUS LES CANDIDATS →",
        )

        for text in expected:
            self.assertIn(text, self.fr)

    def test_source_headlines_remain_source_language(self):
        # Source-originated titles are explicitly marked rather than translated.
        self.assertIn('<h4 lang="fr">', self.en)

    def test_client_side_localization_contract_is_shared(self):
        javascript = JS_PATH.read_text(encoding="utf-8")
        self.assertIn("candidateLocaleTag", javascript)
        self.assertIn('candidateLocale === "en" ? "en-GB" : "fr-FR"', javascript)
        self.assertIn("initCandidateLanguageToggle", javascript)
        self.assertIn("data-candidate-language-peer", self.fr)
        self.assertIn("data-candidate-language-peer", self.en)



if __name__ == "__main__":
    unittest.main()
