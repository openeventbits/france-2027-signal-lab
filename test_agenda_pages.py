from __future__ import annotations

import copy
import inspect
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import urlparse

import build_agenda_pages as builder
from agenda_page_contract import (
    AGENDA_DEFINITIONS,
    AgendaPageContractError,
    POLICY_AGENDA_IDS,
    agenda_manifest_payload,
    project_agenda_pages,
    validate_agenda_manifest,
)


ROOT = Path(__file__).resolve().parent


def normalized(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n")


def canonical(text: str) -> str:
    matches = re.findall(r'<link rel="canonical" href="([^"]+)">', text)
    if len(matches) != 1:
        raise AssertionError(f"expected one canonical, found {len(matches)}")
    return matches[0]


def alternate(text: str, language: str) -> str:
    match = re.search(
        rf'<link rel="alternate" hreflang="{re.escape(language)}" href="([^"]+)">',
        text,
    )
    if not match:
        raise AssertionError(f"missing {language} alternate")
    return match.group(1)


class ProductHierarchy(HTMLParser):
    """Compare bilingual page structure independently of translated prose/URLs."""

    def __init__(self, text):
        super().__init__()
        self.roles = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.roles.append((tag, attrs.get("class"), attrs.get("id"),
                           attrs.get("aria-describedby"), attrs.get("aria-labelledby")))

    def handle_endtag(self, tag):
        self.roles.append(("/" + tag,))


class ProductCopy(HTMLParser):
    """UI text/accessible labels, excluding source data at its actual DOM leaves.

    Keep evidence CTAs, section headers, dates, and empty states in the audit.
    Only publisher names, headlines, candidate names, classifier terms, scripts,
    and the deliberately bilingual language picker are exempt.
    """

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.copy = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        ancestors = set().union(*(entry[1] for entry in self.stack))
        parent = self.stack[-1] if self.stack else None
        excluded = bool(parent and parent[2]) or tag in {"script", "style"}
        excluded |= "candidate-language" in classes
        excluded |= tag == "h3" and "agenda-evidence-row" in ancestors
        excluded |= tag == "strong" and bool(
            {"agenda-evidence-source", "agenda-card-subtopic"} & ancestors)
        excluded |= tag == "span" and "agenda-subtopics-scroll" in ancestors
        excluded |= tag in {"a", "span"} and not classes and bool(
            {"agenda-candidate-column", "agenda-history-candidate-column"} & ancestors)
        if not excluded:
            for attribute in ("aria-label", "title", "alt", "placeholder", "data-label",
                              "data-fr27-tooltip"):
                if attrs.get(attribute):
                    self.copy.append(attrs[attribute])
        if tag not in self.VOID_TAGS:
            self.stack.append((tag, classes, excluded))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        if self.stack and not self.stack[-1][2] and text.strip():
            self.copy.append(" ".join(text.split()))


class HistoricalMarkup(HTMLParser):
    """Check explicitly closed generated markup and retain accessible attributes."""

    def __init__(self, text):
        super().__init__()
        self.elements = []
        self.stack = []
        self.errors = []
        self.feed(text)
        self.errors.extend(f"unclosed {tag}" for tag in self.stack)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))
        if tag not in ProductCopy.VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected closing {tag}")
        else:
            self.stack.pop()


ENGLISH_ONLY_UI = (
    "SOURCE-LINKED", "EVIDENCE", "LATEST", "CURRENT", "HISTORY",
    "HISTORICAL", "HISTORY AVAILABLE", "LONG-RANGE", "LONG RANGE",
    "COVERAGE HISTORY", "COMPACT HISTORY", "PEAK DAYS", "DATA",
    "DAY-BY-DAY LEDGER", "VIEW", "OPEN", "CURRENT ACTIVITY", "CURRENT STATE",
    "CAMPAIGN THEMES", "SINGLE-LABEL", "PREVIOUS WEEK", "RECENT WEEK",
    "ACTIVE TOPIC-DAYS", "HOME", "TOPICS", "CLASSIFIED ITEMS", "SOURCE-DAYS", "ACTIVE DAYS",
    "PUBLISHERS", "AGENDA SHARE", "ASSOCIATED SIGNALS", "OBSERVED CLASSIFICATION",
    "CANDIDATE ASSOCIATIONS", "MOVEMENT DETAIL", "SEARCH TOPICS",
    "NO TOPIC MATCHES", "NO SOURCE-LINKED EVIDENCE", "PUBLICATION CAP",
    "COMPLETE UTC DAYS", "COMPLETE WEEKS", "COVERAGE CADENCE",
    "AGENDA CADENCE", "WEEKLY AGENDA SHARE", "EARLIER", "PARTIAL", "FIRST OBS.", "LAST OBS.",
)
FRENCH_ONLY_UI = (
    "JOURS-THÈMES ACTIFS", "ACTUEL", "ACTUELLE", "HISTORIQUE", "ACTIVITÉ", "JOURS-SOURCES",
    "JOURS ACTIFS", "PART AGENDA", "SEMAINE PRÉC.", "SEMAINE RÉCENTE",
    "SIGNAUX ASSOCIÉS", "ASSOCIATIONS ACTUELLES DE CANDIDATS",
    "DERNIÈRES PREUVES SOURCÉES", "DERNIÈRES OBSERVATIONS SOURCÉES",
    "HISTORIQUE COMPACT", "HISTORIQUE DE LA COUVERTURE", "JOURS MARQUANTS",
    "DONNÉES", "REGISTRE JOUR PAR JOUR", "VOIR", "OUVRIR", "REVENIR",
    "ACCUEIL", "THÈMES", "ARTICLES CLASSÉS", "MÉDIAS", "ÉTIQUETTE UNIQUE",
    "CLASSIFICATION OBSERVÉE", "RECHERCHER UN THÈME", "AUCUN THÈME",
    "AUCUNE PREUVE", "PLAFOND DE PUBLICATION", "LONGUE DURÉE",
    "CADENCE DE COUVERTURE", "DÉTAIL DU MOUVEMENT", "JOURS UTC COMPLETS",
    "SEMAINES COMPLÈTES", "FIL D’ARIANE", "LANGUE DE L’INTERFACE", "FR27 sur X",
    "HEBDOMADAIRE", "ANTÉRIEUR", "PARTIEL", "PRÉCÉDENTE", "DERNIÈRE", "ÉVOLUTION",
)


def language_leaks(text, language):
    labels = ENGLISH_ONLY_UI if language == "fr" else FRENCH_ONLY_UI
    return [(label, value) for value in ProductCopy(text).copy for label in labels
            if re.search(rf"(?<!\w){re.escape(label)}(?!\w)", value, re.I)]


class AgendaPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = builder.build_from_paths(write=False)
        cls.projection = cls.result["projection"]
        cls.manifest = cls.result["manifest"]
        cls.artifacts = cls.result["artifacts"]
        cls.news = json.loads((ROOT / "news_wire.json").read_text(encoding="utf-8"))
        cls.coverage = json.loads(
            (ROOT / "agenda_coverage_history.json").read_text(encoding="utf-8")
        )
        cls.candidate_history = json.loads(
            (ROOT / "candidate_agenda_history.json").read_text(encoding="utf-8")
        )

    def text(self, relative: str | Path) -> str:
        return self.artifacts[Path(relative)].decode("utf-8")

    def assert_serialized_bar_height(self, actual, expected, places):
        # Match the renderer's fixed precision, including Python's half-even ties.
        self.assertEqual(actual, f"{expected:.{places}f}")

    def bar_precision_fixture(self, counts):
        return {"current": {
            "daily_activity": [
                {"date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
                 "source_day_count": count}
                for index, count in enumerate(counts)
            ],
            "comparison": {
                "previous_start": "2026-01-01", "previous_end": "2026-01-07",
                "latest_start": "2026-01-08", "latest_end": "2026-01-14",
            },
        }}

    def test_current_hub_bar_precision_half_even_zero_minimum_and_maximum(self):
        # 5 / 16 * 100 = 31.25, serialized as 31.2 rather than half-up 31.3.
        topic = self.bar_precision_fixture([0, 1, 5, 16])
        for language in ("fr", "en"):
            with self.subTest(language=language):
                bars = builder._current_card_microbars(topic, language)
                self.assertEqual(re.findall(r"--agenda-bar:([\d.]+)%", bars),
                                 ["6.0", "12.0", "31.2", "100.0"])

    def test_current_activity_bar_precision_half_even_zero_and_maximum(self):
        # 18 + 82 * 5 / 16 = 43.625, serialized as 43.62, not 43.63.
        topic = self.bar_precision_fixture([0, 1, 5, 16])
        for language in ("fr", "en"):
            with self.subTest(language=language):
                bars = builder._current_activity_bars(topic, language)
                self.assertEqual(re.findall(r"--agenda-bar:([\d.]+)%", bars),
                                 ["4.00", "23.12", "43.62", "100.00"])

    def test_current_bar_precision_all_zero_series(self):
        topic = self.bar_precision_fixture([0, 0])
        for renderer, expected in ((builder._current_card_microbars, "6.0"),
                                   (builder._current_activity_bars, "4.00")):
            for language in ("fr", "en"):
                with self.subTest(renderer=renderer.__name__, language=language):
                    bars = renderer(topic, language)
                    self.assertEqual(re.findall(r"--agenda-bar:([\d.]+)%", bars),
                                     [expected, expected])

    def test_current_bar_contract_rejects_wrong_value_and_precision(self):
        for language in ("fr", "en"):
            cases = (
                (Path("agenda/index.html" if language == "fr" else "en/agenda/index.html"),
                 self.test_current_hub_card_temporal_boundaries_values_and_order, 1),
                (Path(self.projection["topics"][0]["routes"][language].strip("/")) / "index.html",
                 self.test_current_activity_temporal_dates_and_source_day_heights, 2),
            )
            for path, validate, places in cases:
                text = self.text(path)
                height = re.search(r"--agenda-bar:([\d.]+)%", text).group(1)
                wrong_value = f"{float(height) + 10 ** -places:.{places}f}"
                for wrong in (wrong_value, height + "0"):
                    with self.subTest(path=path, wrong=wrong):
                        changed = dict(self.artifacts)
                        changed[path] = text.replace(f"--agenda-bar:{height}%",
                                                     f"--agenda-bar:{wrong}%", 1).encode("utf-8")
                        with patch.object(self, "artifacts", changed):
                            with self.assertRaises(AssertionError):
                                validate()

    def test_exact_route_census_and_language_split(self):
        self.assertEqual(len(self.artifacts), 28)
        self.assertEqual(
            sum(str(path).replace("\\", "/").startswith("agenda/") for path in self.artifacts),
            14,
        )
        self.assertEqual(
            sum(str(path).replace("\\", "/").startswith("en/agenda/") for path in self.artifacts),
            14,
        )
        self.assertEqual(len(list((ROOT / "agenda").rglob("index.html"))), 14)
        self.assertEqual(len(list((ROOT / "en" / "agenda").rglob("index.html"))), 14)

    def test_manifest_census_formula_and_source_context(self):
        validate_agenda_manifest(self.manifest)
        self.assertEqual(self.manifest["public_topic_count"], 6)
        self.assertEqual(self.manifest["page_count"], 4 * 6 + 4)
        self.assertEqual(len(self.manifest["pages"]), 6)
        self.assertEqual(
            self.manifest["source"]["current"], "news_wire.json:campaign_agenda"
        )
        self.assertEqual(
            self.manifest["source"]["history"], "agenda_coverage_history.json"
        )

    def test_every_public_topic_has_four_locked_routes(self):
        for definition, page in zip(AGENDA_DEFINITIONS, self.manifest["pages"]):
            self.assertEqual(page["topic_id"], definition.topic_id)
            self.assertEqual(page["page_path_fr"], f"/agenda/{definition.slug_fr}/")
            self.assertEqual(page["page_path_en"], f"/en/agenda/{definition.slug_en}/")
            self.assertEqual(
                page["history_page_path_fr"],
                f"/agenda/historique/{definition.slug_fr}/",
            )
            self.assertEqual(
                page["history_page_path_en"],
                f"/en/agenda/history/{definition.slug_en}/",
            )

    def test_six_static_cards_are_in_each_hub(self):
        for relative in (
            "agenda/index.html",
            "en/agenda/index.html",
            "agenda/historique/index.html",
            "en/agenda/history/index.html",
        ):
            text = self.text(relative)
            self.assertEqual(len(re.findall(r" data-agenda-card(?=\s|>)", text)), 6, relative)
            for definition in AGENDA_DEFINITIONS:
                slug = definition.slug_fr if not relative.startswith("en/") else definition.slug_en
                history = "historique" in relative or "history" in relative
                expected = (
                    f"/agenda/historique/{slug}/"
                    if history and not relative.startswith("en/")
                    else f"/en/agenda/history/{slug}/"
                    if history
                    else f"/agenda/{slug}/"
                    if not relative.startswith("en/")
                    else f"/en/agenda/{slug}/"
                )
                self.assertIn(f'href="{expected}"', text)

    def test_current_hub_required_structure_and_order(self):
        for relative in ("agenda/index.html", "en/agenda/index.html"):
            text = self.text(relative)
            markers = (
                "polling-breadcrumb",
                "polling-intro agenda-intro",
                "polling-metrics agenda-metrics",
                "agenda-landscape-panel",
                "agenda-movement-panel",
                "agenda-agenda-panel",
                "agenda-latest",
                "agenda-history-gateway",
                "fr27-app-hud",
            )
            positions = [text.index(marker) for marker in markers]
            self.assertEqual(positions, sorted(positions))

    def assert_panel_copy(self, document, marker, eyebrow, title, status=None):
        panel = document.split(marker, 1)[1].split("</h2>", 1)
        self.assertIn(f'>{eyebrow}</div>', panel[0])
        self.assertRegex(panel[0], rf'<h2(?: [^>]*)?>{re.escape(_escaped(title))}$')
        if status is not None:
            self.assertRegex(panel[1], rf'class="(?:polling|poll-detail)-panel-status">{re.escape(status)}</span>')

    def test_current_hub_bilingual_product_vocabulary(self):
        for language, path in (("fr", "agenda/index.html"), ("en", "en/agenda/index.html")):
            french = language == "fr"
            text = self.text(path)
            self.assert_panel_copy(text, "agenda-movement-panel",
                "COMPARAISON · SEMAINES COMPLÈTES" if french else "COMPARISON · COMPLETE WEEKS",
                "CE QUI BOUGE" if french else "WHAT’S MOVING",
                "PART AGENDA" if french else "AGENDA SHARE")
            self.assert_panel_copy(text, "agenda-agenda-panel",
                "CE DONT PARLE LA CAMPAGNE" if french else "CAMPAIGN THEMES",
                "AGENDA DE CAMPAGNE" if french else "CAMPAIGN AGENDA",
                "ÉTIQUETTE UNIQUE" if french else "SINGLE-LABEL")
            self.assert_panel_copy(text, "agenda-latest", "SOURCES" if french else "SOURCE-LINKED",
                "DERNIÈRES OBSERVATIONS SOURCÉES" if french else "LATEST SOURCE-LINKED OBSERVATIONS",
                "8 ÉLÉMENTS" if french else "8 ITEMS")
            self.assertEqual(text.count('class="agenda-evidence-row agenda-hub-evidence-row"'), 8)
            self.assert_panel_copy(text, "agenda-history-gateway is-compact",
                "HISTORIQUE DISPONIBLE" if french else "HISTORY AVAILABLE",
                "HISTORIQUE DE L’AGENDA" if french else "AGENDA HISTORY",
                f'{(date.fromisoformat(self.projection["coverage_history_period"]["end_date"]) - date.fromisoformat(self.projection["coverage_history_period"]["start_date"])).days + 1} ' + ("JOURS" if french else "DAYS"))
            self.assertIn("EXPLORER L’HISTORIQUE →" if french else "EXPLORE HISTORY →", text)

    def test_current_hub_card_temporal_boundaries_values_and_order(self):
        for language, path in [('fr', 'agenda/index.html'), ('en', 'en/agenda/index.html')]:
            cards = re.findall(r'<a class="agenda-card"(.*?)</a>', self.text(path), re.S)
            topics = [topic for topic in self.projection['topics'] if topic['public']]
            self.assertEqual(len(cards), 6)
            self.assertEqual([html_unescape(re.search(r'href="([^"]+)"', card).group(1)) for card in cards],
                             [topic['routes'][language] for topic in topics])
            for card, topic in zip(cards, topics):
                current = topic['current']
                comparison = current['comparison']
                counts = card.split('class="agenda-card-counts">', 1)[1].split('</span></span>', 1)[0]
                self.assertEqual(re.findall(r'<strong\b[^>]*>(.*?)</strong>', counts),
                                 [str(current['source_day_count']), str(current['publisher_count'])])
                self.assertIn(f'data-sort-volume="{current["item_count"]}"', card)
                self.assertIn(f'data-sort-activity="{comparison["latest_agenda_share"]:.8f}"', card)
                self.assertIn(f'data-sort-movement="{abs(comparison["agenda_share_change_pp"]):.4f}"', card)
                bars = re.findall(r'<i class="(is-\w+)" data-date="([^"]+)" data-source-days="(\d+)" style="--agenda-bar:([\d.]+)%"', card)
                series = current['daily_activity']
                self.assertEqual([(day, int(value)) for _, day, value, _ in bars],
                                 [(point['date'], point['source_day_count']) for point in series])
                maximum = max(point['source_day_count'] for point in series) or 1
                periods = {}
                for actual, day, value, height in bars:
                    expected = ('is-older' if day < comparison['previous_start'] else
                                'is-previous' if day <= comparison['previous_end'] else
                                'is-recent' if day <= comparison['latest_end'] else 'is-partial')
                    self.assertEqual(actual, expected, (language, topic['topic_id'], day))
                    expected_height = 6 if int(value) == 0 else max(12, int(value) / maximum * 100)
                    self.assert_serialized_bar_height(height, expected_height, places=1)
                    periods[day] = actual
                for boundary, expected in [('previous_start', 'is-previous'), ('previous_end', 'is-previous'),
                                           ('latest_start', 'is-recent'), ('latest_end', 'is-recent')]:
                    self.assertEqual(periods[comparison[boundary]], expected)
                self.assertEqual(set(periods.values()), {'is-older', 'is-previous', 'is-recent', 'is-partial'})
                window = card.split('class="agenda-card-window">', 1)[1].split('class="agenda-card-subtopic"', 1)[0]
                self.assertIn(builder._decimal(comparison['latest_agenda_share'] * 100, language) + '%', window)
                self.assertIn(builder._signed(comparison['agenda_share_change_pp'], language, 'pp'), window)
                self.assertIn(_escaped(current['matched_term_counts'][0]['term']), card)

    def test_current_hub_evidence_exact_source_rows_and_history_route(self):
        for language, path in [('fr', 'agenda/index.html'), ('en', 'en/agenda/index.html')]:
            text = self.text(path)
            rows = re.findall(r'<article class="agenda-evidence-row agenda-hub-evidence-row">(.*?)</article>', text)
            self.assertEqual(len(rows), 8)
            expected = self.projection['latest_evidence'][:8]
            self.assertEqual([html_unescape(re.search(r'class="agenda-evidence-external" href="([^"]+)"', row).group(1)) for row in rows],
                             [item['url'] for item in expected])
            topics = {topic['topic_id']: topic for topic in self.projection['topics']}
            for row, item in zip(rows, expected):
                self.assertIn(f'<h3>{_escaped(item["headline"])}</h3>', row)
                self.assertIn(f'<strong>{_escaped(item["publisher"])}</strong>', row)
                self.assertEqual(re.findall(r'class="agenda-evidence-agenda" href="([^"]+)"', row),
                                 [topics[topic_id]['routes'][language] for topic_id in item['topic_ids']])
            gateway = text.split('agenda-history-gateway is-compact', 1)[1]
            self.assertIn('href="/agenda/historique/"' if language == 'fr' else 'href="/en/agenda/history/"', gateway)

    def test_current_hub_card_component_preserves_issues_geometry_and_three_columns(self):
        css = (ROOT / 'assets/agenda.css').read_text(encoding='utf-8')
        current = css.split('FR27 AGENDA CURRENT HUB — MANUAL VISUAL PASS 01', 1)[1]
        desktop = re.search(r'@media \(min-width: 1100px\)\s*\{\s*\.agenda-hub-page:not\(\.agenda-history-page\) \.agenda-card-grid\s*\{([^}]+)\}', current)
        self.assertIsNotNone(desktop)
        self.assertIn('grid-template-columns: repeat(3, minmax(0, 1fr));', desktop.group(1))
        self.assertNotRegex(current, r'\.agenda-hub-page:not\(\.agenda-history-page\)\s+\.agenda-card(?:[\s.{:]|-(?!grid\b))')
        # Shared baseline owns padding, typography, 48px plot and temporal colors.
        self.assertIn('grid-template-rows: auto auto 48px auto auto auto;', css)
        self.assertIn('background: rgba(139, 121, 255, .78);', css)
        self.assertIn('background: rgba(53, 216, 255, .88);', css)
        self.assertRegex(current, r'\.agenda-hub-page:not\(\.agenda-history-page\) \.agenda-hub-title-row > \.agenda-note-tooltip\s*\{\s*position: static;\s*\}')

    def test_current_hub_bar_renderer_cannot_change_detail_or_history_outputs(self):
        hubs = {Path('agenda/index.html'), Path('en/agenda/index.html')}
        with patch.object(builder, '_current_card_microbars', return_value='<div>hub-only probe</div>'):
            changed = builder.build_from_paths(write=False)['artifacts']
        self.assertEqual({path for path in self.artifacts if changed[path] != self.artifacts[path]}, hubs)
        for path in self.artifacts.keys() - hubs:
            self.assertEqual(changed[path], self.artifacts[path], path)

    def test_current_detail_bilingual_product_vocabulary(self):
        for topic in self.projection["topics"]:
            for language in ("fr", "en"):
                french = language == "fr"
                text = self.text(Path(topic["routes"][language].strip("/")) / "index.html")
                for marker, eyebrow, title in (
                    ("agenda-current-activity", "ACTIVITÉ · 30 J" if french else "ACTIVITY · 30D", "ACTIVITÉ ACTUELLE" if french else "CURRENT ACTIVITY"),
                    ("agenda-subtopics", "CLASSIFICATION OBSERVÉE" if french else "OBSERVED CLASSIFICATION", "SIGNAUX ASSOCIÉS" if french else "ASSOCIATED SIGNALS"),
                    ("agenda-current-candidates", "CO-OCCURRENCE CANDIDATS · 30 J" if french else "CANDIDATE CO-OCCURRENCE · 30D", "ASSOCIATIONS ACTUELLES DE CANDIDATS" if french else "CURRENT CANDIDATE ASSOCIATIONS"),
                    ("agenda-current-evidence", "SOURCES" if french else "SOURCE-LINKED", "DERNIÈRES PREUVES SOURCÉES" if french else "LATEST SOURCE-LINKED EVIDENCE"),
                    ("agenda-compact-history\"", "LONGUE DURÉE" if french else "LONG-RANGE", "HISTORIQUE COMPACT" if french else "COMPACT HISTORY"),
                ):
                    self.assert_panel_copy(text, marker, eyebrow, title)
                self.assertIn("VOIR L’HISTORIQUE DE CE THÈME →" if french else "VIEW THIS TOPIC’S HISTORY →", text)

    def test_history_hub_period_copy_and_tooltip_only_methodology(self):
        period = self.projection["coverage_history_period"]
        days = (date.fromisoformat(period["end_date"]) - date.fromisoformat(period["start_date"])).days + 1
        for language, path in (("fr", "agenda/historique/index.html"), ("en", "en/agenda/history/index.html")):
            french = language == "fr"
            text = self.text(path)
            self.assert_panel_copy(text, "agenda-landscape-panel",
                f"{days} J UTC" if french else f"{days} UTC DAYS",
                "PAYSAGE HISTORIQUE DES THÈMES" if french else "HISTORICAL TOPIC LANDSCAPE",
                f"6 THÈMES · {days} J" if french else f"6 TOPICS · {days} DAYS")
            self.assert_panel_copy(text, "agenda-movement-panel",
                "COMPARAISON · JOURS UTC COMPLETS" if french else "COMPARISON · COMPLETE UTC DAYS",
                "ÉVOLUTION HISTORIQUE" if french else "HISTORICAL MOVEMENT",
                "PART AGENDA" if french else "AGENDA SHARE")
            self.assert_panel_copy(text, "agenda-agenda-panel",
                "COMPOSITION HISTORIQUE" if french else "HISTORICAL COMPOSITION",
                "CADENCE DE L’AGENDA" if french else "AGENDA CADENCE",
                "ÉTIQUETTE UNIQUE" if french else "SINGLE-LABEL")
            self.assertIn("OBSERVATIONS HISTORIQUES SOURCÉES" if french else "SOURCE-LINKED HISTORICAL OBSERVATIONS", text)
            self.assertNotIn("PÉRIMÈTRE HISTORIQUE", text)
            self.assertNotIn("HISTORICAL BOUNDARY", text)
            self.assertIn("jours UTC complets" if french else "complete UTC days", text)
            self.assertIn('id="agenda-hub-method" role="tooltip"', text)
            self.assert_panel_copy(text, "agenda-history-gateway is-compact",
                "PROJECTION ACTUELLE" if french else "CURRENT PROJECTION",
                "AGENDA ACTUEL" if french else "CURRENT AGENDA", "30 J" if french else "30D")
            self.assertIn("REVENIR AUX 30 DERNIERS JOURS" if french else "RETURN TO THE LATEST 30 DAYS", text)
            self.assertIn("VOIR L’AGENDA ACTUEL →" if french else "VIEW CURRENT AGENDA →", text)

        # Changing the input period proves the landscape is not tied to today's 72 days.
        changed = copy.deepcopy(self.projection)
        changed_start = date.fromisoformat(period["start_date"]) + timedelta(days=1)
        changed["coverage_history_period"]["start_date"] = changed_start.isoformat()
        shell = builder.load_shell_templates(ROOT)["en"]
        text = builder._hub_common(changed, language="en", shell=shell,
                                   favicon="", og_image="", history=True).decode("utf-8")
        changed_days = days - 1
        self.assertIn(f'>{changed_days} UTC DAYS</div>', text)
        self.assertIn(f'6 TOPICS · {changed_days} DAYS</span>', text)

    def test_history_cards_temporal_windows_and_unchanged_metrics(self):
        for language, path in (("fr", "agenda/historique/index.html"), ("en", "en/agenda/history/index.html")):
            cards = re.findall(r'<a class="agenda-card".*?</a>', self.text(path), re.S)
            self.assertEqual(len(cards), 6)
            for topic, card in zip(self.projection["topics"], cards):
                history = topic["coverage_history"]
                comparison = topic["history_comparison"]
                bars = re.findall(r'<i class="(is-[a-z]+)" data-date="([^"]+)" data-source-days="(\d+)"', card)
                self.assertEqual(len(bars), len(history["daily"]))
                counts = {"is-older": 0, "is-previous": 0, "is-recent": 0}
                for (period_class, day, value), point in zip(bars, history["daily"]):
                    expected = "is-older"
                    if comparison["previous_start"] <= point["date"] <= comparison["previous_end"]:
                        expected = "is-previous"
                    elif comparison["latest_start"] <= point["date"] <= comparison["latest_end"]:
                        expected = "is-recent"
                    self.assertEqual((period_class, day, int(value)), (expected, point["date"], point["source_day_count"]))
                    counts[period_class] += 1
                self.assertEqual(counts["is-previous"], 28)
                self.assertEqual(counts["is-recent"], 28)
                self.assertGreater(counts["is-older"], 0)
                self.assertNotIn("is-partial", card)
                self.assertIn(f'<strong>{history["total_source_days"]}</strong>', card)
                self.assertIn(f'<strong>{history["active_days"]}</strong>', card)
                self.assertIn(f'data-sort-volume="{history["total_items"]}"', card)
                self.assertIn(builder._h(builder._decimal(comparison["latest_agenda_share"] * 100, language)) + "%", card)
                self.assertIn(builder._h(builder._signed(comparison["agenda_share_change_pp"], language, "pp")), card)
                peak = f'{history["peak_day"]["source_day_count"]} · {builder._date(history["peak_day"]["date"], language)}'
                self.assertIn(builder._h(peak), card)
                for field, start, end in (("previous", "previous_start", "previous_end"), ("latest", "latest_start", "latest_end")):
                    total = sum(point["source_day_count"] for point in history["daily"] if comparison[start] <= point["date"] <= comparison[end])
                    self.assertEqual(total, comparison[field + "_source_day_count"])

    def test_history_composition_reconciles_correct_denominators_and_rank(self):
        ordered = sorted(self.projection["topics"], key=lambda topic: (-topic["history_comparison"]["latest_agenda_share"], topic["topic_id"]))
        for language in ("fr", "en"):
            panel = builder._historical_composition(self.projection["topics"], language)
            ranked = re.findall(r'<div class="agenda-agenda-topic" data-topic-id="([^"]+)">', panel)
            self.assertEqual(ranked, [topic["topic_id"] for topic in ordered])
            for prefix, field in (("previous", "previous"), ("recent", "latest")):
                reference = ordered[0]["history_comparison"]
                start, end = reference[field + "_start"], reference[field + "_end"]
                denominator = sum(point["source_day_count"] for topic in ordered for point in topic["coverage_history"]["daily"] if start <= point["date"] <= end)
                self.assertIn(f' · n={denominator}</small>', panel)
                self.assertIn(builder._h(builder._period(start, end, language)), panel)
                segments = re.findall(rf'class="agenda-agenda-segment is-{prefix}" data-topic-id="([^"]+)" style="--agenda-share:([0-9.]+)%"', panel)
                self.assertEqual([topic_id for topic_id, _ in segments], ranked)
                self.assertAlmostEqual(sum(float(share) for _, share in segments), 100, places=5)
                for topic, (topic_id, percent) in zip(ordered, segments):
                    numerator = sum(point["source_day_count"] for point in topic["coverage_history"]["daily"] if start <= point["date"] <= end)
                    self.assertAlmostEqual(float(percent), numerator / denominator * 100, places=5)
                    self.assertAlmostEqual(topic["history_comparison"][field + "_agenda_share"], numerator / denominator)
            self.assertIn("28 J ANTÉRIEURS" if language == "fr" else "EARLIER 28D", panel)
            self.assertIn("28 J RÉCENTS" if language == "fr" else "RECENT 28D", panel)
            self.assertNotIn("heat-strip", panel)
            movement = builder._movement_chart(self.projection["topics"], language, history=True)
            for topic in ordered:
                comparison = topic["history_comparison"]
                self.assertIn(builder._h(builder._signed(comparison["agenda_share_change_pp"], language, "pp")), movement)
                for field in ("previous_agenda_share", "latest_agenda_share"):
                    self.assertIn(builder._h(builder._decimal(comparison[field] * 100, language)) + "%", movement)

    def test_history_components_cannot_change_locked_page_families(self):
        with patch.object(builder, "_historical_card_microbars", return_value="<div>history chart sentinel</div>"), patch.object(builder, "_historical_composition", return_value="<div>history composition sentinel</div>"), patch.object(builder, "_historical_evidence", return_value=[]):
            result = builder.build_from_paths(write=False)
        changed = {path.as_posix() for path in self.artifacts if self.artifacts[path] != result["artifacts"][path]}
        self.assertEqual(changed, {"agenda/historique/index.html", "en/agenda/history/index.html"})
        self.assertEqual(self.manifest, result["manifest"])

    def test_history_evidence_has_retained_snapshot_authority_and_theme_coverage(self):
        rows = self.projection["historical_evidence"]
        self.assertEqual(len(rows), 6)
        self.assertEqual({row["topic_ids"][0] for row in rows}, {topic["topic_id"] for topic in self.projection["topics"]})
        self.assertEqual(rows, sorted(rows, key=lambda row: (row["date"], row["published_at"], str(row["id"])), reverse=True))
        authority = {point["date"]: point["source_snapshot_at"] for point in self.coverage["daily"]}
        for row, original in zip(rows, self.coverage["historical_evidence"]["items"]):
            self.assertLessEqual(
                datetime.fromisoformat(
                    row["source_snapshot_at"].replace(
                        "Z",
                        "+00:00",
                    )
                ),
                datetime.fromisoformat(
                    authority[row["date"]].replace(
                        "Z",
                        "+00:00",
                    )
                ),
            )
            self.assertEqual(row["topic_ids"], [original["topic_id"]])
            for field in ("id", "url", "headline", "publisher", "published_at", "date", "source_snapshot_at", "source_commit"):
                self.assertEqual(row[field], original[field])
        # At least one row must come from an older retained snapshot, not current-only evidence.
        self.assertTrue(any(row["source_snapshot_at"] != self.news["generated_at"] for row in rows))
        for language, path in (("fr", "agenda/historique/index.html"), ("en", "en/agenda/history/index.html")):
            text = self.text(path)
            articles = re.findall(r'<article class="agenda-evidence-row agenda-hub-evidence-row">(.*?)</article>', text)
            self.assertEqual(len(articles), 6)
            for row, article in zip(rows, articles):
                self.assertIn(builder._h(row["url"]), article)
                topic = next(topic for topic in self.projection["topics"] if topic["topic_id"] == row["topic_ids"][0])
                self.assertIn(topic["routes"]["history_fr" if language == "fr" else "history_en"], article)
            self.assertIn(f'class="agenda-history-gateway-cta" href="{"/agenda/" if language == "fr" else "/en/agenda/"}"', text)

    def test_page_builder_renders_without_git_history_access(self):
        source = inspect.getsource(builder)
        self.assertNotIn("build_agenda_coverage_history", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("_retained_agenda_snapshots", source)
        with patch.object(subprocess, "Popen", side_effect=AssertionError("page renderer must not call Git")), patch.object(subprocess, "check_output", side_effect=AssertionError("page renderer must not call Git")), patch.object(subprocess, "run", side_effect=AssertionError("page renderer must not call Git")):
            result = builder.build_from_paths(write=False)
        self.assertEqual(self.artifacts, result["artifacts"])
        self.assertEqual(result["projection"]["historical_evidence"], self.projection["historical_evidence"])

    def test_page_builder_evidence_cannot_fall_back_to_current_or_partial_census(self):
        malformed = copy.deepcopy(self.coverage)
        malformed["historical_evidence"]["items"].pop()
        with patch.object(builder, "_load_json", side_effect=lambda path: malformed if Path(path) == builder.COVERAGE_HISTORY_PATH else json.loads(Path(path).read_text(encoding="utf-8"))):
            with self.assertRaises(AgendaPageContractError):
                builder.build_from_paths(write=False)
        with self.assertRaisesRegex(builder.AgendaPageBuildError, "every public Agenda topic"):
            builder._historical_evidence(malformed, self.projection["topics"])

    def test_historical_hub_aggregate_active_topic_days_are_not_calendar_days(self):
        aggregate = sum(topic["coverage_history"]["active_days"] for topic in self.projection["topics"])
        expected = sum(topic["active_days"] for topic in self.coverage["topics"] if topic["historical_qualified"])
        self.assertEqual(aggregate, expected)
        for language, path in (("fr", "agenda/historique/index.html"), ("en", "en/agenda/history/index.html")):
            label = "JOURS-THÈMES ACTIFS" if language == "fr" else "ACTIVE TOPIC-DAYS"
            metric = f'<span class="polling-metric-label">{label}</span><strong>{aggregate}</strong>'
            self.assertIn(metric, self.text(path))
            old_label = "JOURS ACTIFS" if language == "fr" else "ACTIVE DAYS"
            self.assertNotIn(f'<span class="polling-metric-label">{old_label}</span>', self.text(path))
            for topic in self.projection["topics"]:
                card = builder._topic_card(topic, language, history=True)
                self.assertIn(f'<strong>{topic["coverage_history"]["active_days"]}</strong><small>{old_label}</small>', card)
                self.assertIn(old_label, self.text("agenda/historique/" + topic["slugs"]["fr"] + "/index.html" if language == "fr" else "en/agenda/history/" + topic["slugs"]["en"] + "/index.html"))

    def test_history_css_keeps_issues_geometry_palette_and_three_columns(self):
        css = (ROOT / "assets/agenda.css").read_text(encoding="utf-8")
        self.assertRegex(css, r'@media \(min-width: 1100px\)\s*\{\s*\.agenda-history-page \.agenda-card-grid\s*\{\s*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\);')
        self.assertNotIn(".agenda-history-page .agenda-agenda-panel .agenda-history-evolution-rows", css)
        self.assertNotIn(".agenda-history-page .agenda-agenda-panel .agenda-history-evolution-row", css)
        self.assertIn(".agenda-agenda-segment.is-previous {\n  background: rgba(139, 121, 255, .82);", css)
        self.assertIn(".agenda-agenda-segment.is-recent {\n  background: rgba(53, 216, 255, .82);", css)
        self.assertRegex(css, r'\.agenda-history-page \.agenda-hub-title-row > \.agenda-note-tooltip\s*\{\s*position: static;')

    def test_history_detail_bilingual_product_vocabulary(self):
        for topic in self.projection["topics"]:
            for language, key in (("fr", "history_fr"), ("en", "history_en")):
                french = language == "fr"
                text = self.text(Path(topic["routes"][key].strip("/")) / "index.html")
                for marker, eyebrow, title in (
                    ("agenda-history-detail-evolution", "LONGITUDINAL", "HISTORIQUE DE LA COUVERTURE" if french else "COVERAGE HISTORY"),
                    ("agenda-history-peaks", "REPÈRES" if french else "HIGHLIGHTS", "JOURS MARQUANTS" if french else "PEAK DAYS"),
                    ("agenda-history-candidates", "DOMAINE SÉPARÉ" if french else "SEPARATE DOMAIN", "HISTORIQUE DES ASSOCIATIONS CANDIDAT × THÈME" if french else "CANDIDATE × TOPIC ASSOCIATION HISTORY"),
                    ("agenda-history-daily", "DONNÉES" if french else "DATA", "REGISTRE JOUR PAR JOUR" if french else "DAY-BY-DAY LEDGER"),
                ):
                    self.assert_panel_copy(text, marker, eyebrow, title)
                self.assertIn("VOIR L’ÉTAT ACTUEL →" if french else "VIEW CURRENT STATE →", text)
                self.assertIn("TOUT L’HISTORIQUE DE L’AGENDA →" if french else "ALL AGENDA HISTORY →", text)

    def test_all_french_routes_have_no_english_structural_ui(self):
        for path in self.artifacts:
            if path.as_posix().startswith("agenda/"):
                with self.subTest(route=path):
                    self.assertEqual(language_leaks(self.text(path), "fr"), [])

    def test_all_english_routes_have_no_french_structural_ui(self):
        for path in self.artifacts:
            if path.as_posix().startswith("en/agenda/"):
                with self.subTest(route=path):
                    self.assertEqual(language_leaks(self.text(path), "en"), [])

    def test_copy_audit_excludes_source_leaves_but_keeps_surrounding_ui(self):
        # Deliberate language-looking source data must not mask UI leaks nearby.
        for language, phrase in (("en", "HISTORIQUE ACTUEL ACTIVITÉ"),
                                 ("fr", "HISTORY CURRENT EVIDENCE")):
            source_markup = f'''
                <article class="agenda-evidence-row">
                  <div class="agenda-evidence-source"><strong>{phrase}</strong></div>
                  <h3>{phrase}</h3><a href="https://example.com/">SOURCE ↗</a>
                </article>
                <span class="agenda-card-subtopic"><small>SIGNAL</small><strong>{phrase}</strong></span>
                <ol class="agenda-subtopics-scroll"><li><div><span>{phrase}</span><strong>2</strong></div></li></ol>
                <ul class="agenda-candidate-column"><li><a href="/candidate/">{phrase}</a><strong>2 associations</strong></li></ul>
                <ul class="agenda-history-candidate-column"><li><div class="agenda-history-candidate-primary"><span>{phrase}</span></div></li></ul>
            '''
            with self.subTest(language=language):
                self.assertEqual(language_leaks(source_markup, language), [])
                for ui in (
                    f'<div class="poll-detail-eyebrow">{phrase}</div>',
                    f'<h2>{phrase}</h2>',
                    f'<button aria-label="{phrase}">i</button>',
                    f'<span role="tooltip">{phrase}</span>',
                    f'<a data-fr27-tooltip="{phrase}">SOURCE ↗</a>',
                    f'<td data-label="{phrase}">2</td>',
                    f'<input placeholder="{phrase}">',
                    f'<article class="agenda-evidence-row"><a>{phrase}</a></article>',
                    f'<ol class="agenda-subtopics-scroll"><p class="agenda-detail-note">{phrase}</p></ol>',
                ):
                    self.assertTrue(language_leaks(source_markup + ui, language), ui)

    def test_current_evidence_header_and_omissions_stay_outside_scroll_body(self):
        for topic in self.projection["topics"]:
            for language in ("fr", "en"):
                text = self.text(Path(topic["routes"][language].strip("/")) / "index.html")
                section = text.split('agenda-published-evidence agenda-current-evidence', 1)[1].split('</section>', 1)[0]
                body_start = '<div class="agenda-evidence-list agenda-current-evidence-visible">'
                header, body = section.split(body_start, 1)
                self.assertIn('class="poll-detail-panel-head"', header)
                self.assertIn('class="poll-detail-panel-status"', header)
                self.assertNotIn('<h2', body)
                self.assertRegex(body, r'(?:</article>|</p>)</div>$')
                omitted = topic["current"]["omitted_item_count"]
                self.assertEqual('id="agenda-evidence-cap-note" role="tooltip"' in header, bool(omitted))
                self.assertNotIn("agenda-evidence-cap-note", body)
                if omitted:
                    self.assertIn('aria-describedby="agenda-evidence-cap-note"', header)
                    self.assertIn(f'{omitted} ' + ('éléments supplémentaires' if language == 'fr' else 'additional items'), header)

    def current_details(self):
        for topic in self.projection["topics"]:
            for language in ("fr", "en"):
                yield topic, language, self.text(Path(topic["routes"][language].strip("/")) / "index.html")

    def test_current_hero_weekly_share_two_cells(self):
        for topic, language, text in self.current_details():
            french = language == "fr"
            comparison = topic["current"]["comparison"]
            hero = text.split('class="agenda-weekly-signal"', 1)[1].split('</section>', 1)[0]
            self.assertIn('PART AGENDA HEBDOMADAIRE' if french else 'WEEKLY AGENDA SHARE', hero)
            self.assertIn('id="agenda-weekly-signal-note" role="tooltip"', hero)
            values = hero.split('class="agenda-weekly-signal-values">', 1)[1]
            self.assertEqual(re.findall(r'<span>(.*?)</span>', values), [
                'DERNIÈRE SEM. COMPLÈTE' if french else 'LATEST COMPLETE WEEK',
                'VS SEM. COMPLÈTE PRÉC.' if french else 'VS PREVIOUS COMPLETE WEEK'])
            share = f'{comparison["latest_agenda_share"] * 100:.1f}'
            change = comparison["agenda_share_change_pp"]
            delta = ('+' if change > 0 else '−' if change < 0 else '') + f'{abs(change):.1f}'
            if french:
                share, delta = share.replace('.', ','), delta.replace('.', ',')
            self.assertEqual(re.findall(r'<strong>(.*?)</strong>', values), [share + '%', delta + 'pp'])
            self.assertNotIn('→', values)
            self.assertNotRegex(values, r'JOURS-SOURCES|SOURCE-DAYS')

    def test_current_activity_temporal_dates_and_source_day_heights(self):
        for topic, language, text in self.current_details():
            series = topic["current"]["daily_activity"]
            comparison = topic["current"]["comparison"]
            bars = re.findall(r'<i class="agenda-detail-activity-bar (is-\w+)" data-date="([^"]+)" data-source-days="(\d+)" style="--agenda-bar:([\d.]+)%"', text)
            self.assertEqual([bar[1] for bar in bars], [point['date'] for point in series])
            maximum = max(point['source_day_count'] for point in series) or 1
            classes = {}
            for (actual, day, value, height), point in zip(bars, series):
                expected = ('is-older' if day < comparison['previous_start'] else
                            'is-previous' if day <= comparison['previous_end'] else
                            'is-latest' if day <= comparison['latest_end'] else 'is-partial')
                self.assertEqual(actual, expected, (topic['topic_id'], language, day))
                self.assertEqual(int(value), point['source_day_count'])
                expected_height = 4 if int(value) == 0 else 18 + 82 * int(value) / maximum
                self.assert_serialized_bar_height(height, expected_height, places=2)
                classes[day] = actual
            for boundary, expected in [('previous_start', 'is-previous'), ('previous_end', 'is-previous'),
                                       ('latest_start', 'is-latest'), ('latest_end', 'is-latest')]:
                self.assertEqual(classes[comparison[boundary]], expected)
            self.assertEqual(set(classes.values()), {'is-older', 'is-previous', 'is-latest', 'is-partial'})
            legend = text.split('class="agenda-current-activity-legend"', 1)[1].split('</div>', 1)[0]
            self.assertEqual(re.findall(r'</i>(.*?)</span>', legend),
                ['ANTÉRIEUR', 'SEM. COMPLÈTE PRÉC.', 'DERNIÈRE SEM. COMPLÈTE', 'PARTIEL'] if language == 'fr' else
                ['EARLIER', 'PREVIOUS COMPLETE WEEK', 'LATEST COMPLETE WEEK', 'PARTIAL'])

    def test_current_activity_absolute_weekly_summary(self):
        for topic, language, text in self.current_details():
            comparison = topic['current']['comparison']
            activity = text.split('class="agenda-current-incidence"', 1)[1].split('</section>', 1)[0]
            self.assertIn('JOURS-SOURCES · SEMAINES COMPLÈTES' if language == 'fr' else 'SOURCE-DAYS · COMPLETE WEEKS', activity)
            self.assertEqual(re.findall(r'<dt>(.*?)</dt>', activity),
                ['PRÉCÉDENTE', 'DERNIÈRE', 'ÉVOLUTION'] if language == 'fr' else ['PREVIOUS', 'LATEST', 'CHANGE'])
            change = comparison['latest_source_day_count'] - comparison['previous_source_day_count']
            delta = ('+' if change > 0 else '−' if change < 0 else '') + str(abs(change))
            self.assertEqual(re.findall(r'<dd>(.*?)</dd>', activity),
                [str(comparison['previous_source_day_count']), str(comparison['latest_source_day_count']), delta])
            self.assertNotRegex(activity, r'PART AGENDA|AGENDA SHARE|%|pp<')

    def test_current_compact_history_coverage_metrics_and_daily_series(self):
        for topic, language, text in self.current_details():
            history = topic['coverage_history']
            section = text.split('class="poll-detail-panel agenda-compact-history"', 1)[1].split('</section>', 1)[0]
            first, last = [builder._date(history[key], language) for key in ('first_observation', 'last_observation')]
            self.assertIn(f'class="poll-detail-panel-status">{first} → {last}</span>', section)
            self.assertEqual(re.findall(r'<dt>(.*?)</dt>', section),
                ['PREMIÈRE OBS.', 'DERNIÈRE OBS.', 'JOURS-SOURCES', 'JOURS ACTIFS'] if language == 'fr' else
                ['FIRST OBS.', 'LAST OBS.', 'SOURCE-DAYS', 'ACTIVE DAYS'])
            self.assertEqual(re.findall(r'<dd>(.*?)</dd>', section), [first, last, str(history['total_source_days']), str(history['active_days'])])
            bars = re.findall(r'class="agenda-compact-history-bar" data-date="([^"]+)" data-source-days="(\d+)" style="--agenda-bar:([\d.]+)%"', section)
            self.assertEqual([(day, int(value)) for day, value, _ in bars],
                [(point['date'], point['source_day_count']) for point in history['daily']])
            maximum = max(point['source_day_count'] for point in history['daily']) or 1
            for _, value, height in bars:
                self.assertAlmostEqual(float(height), 4 if int(value) == 0 else 16 + 84 * int(value) / maximum, places=2)

    def test_current_bottom_navigation_localized_routes(self):
        for topic, language, text in self.current_details():
            navigation = text.split('class="agenda-detail-crosslinks">', 1)[1].split('</div>', 1)[0]
            self.assertEqual(re.findall(r'href="([^"]+)"', navigation),
                [topic['routes']['history_fr' if language == 'fr' else 'history_en'], '/agenda/' if language == 'fr' else '/en/agenda/'])
            self.assertEqual(re.findall(r'>([^<>]+)</a>', navigation),
                ['VOIR L’HISTORIQUE DE CE THÈME →', 'TOUS LES THÈMES DE L’AGENDA →'] if language == 'fr' else
                ['VIEW THIS TOPIC’S HISTORY →', 'ALL AGENDA TOPICS →'])

    def test_current_candidate_adaptive_columns_share_global_magnitude_scale(self):
        candidates = max((topic['current_candidate_associations']['candidates'] for topic in self.projection['topics']), key=len)
        self.assertGreaterEqual(len(candidates), 7)
        for size in (1, 6, 7, len(candidates)):
            data = {'candidates': candidates[:size]}
            rendered = builder._candidate_columns(data, 'en')
            columns = re.findall(r'<ul class="agenda-candidate-column">(.*?)</ul>', rendered)
            expected = [size] if size <= 6 else [(size + 1) // 2, size // 2]
            self.assertEqual([column.count('<li>') for column in columns], expected)
            values = [float(value) for value in re.findall(r'--agenda-candidate-share:([\d.]+)', rendered)]
            self.assertEqual(values, [round(candidate['association_count'] / candidates[0]['association_count'], 6) for candidate in candidates[:size]])

    def test_current_evidence_desktop_and_mobile_scroll_css_contract(self):
        css = (ROOT / "assets/agenda.css").read_text(encoding="utf-8")
        selector = ".agenda-current-detail-page .agenda-current-evidence .agenda-current-evidence-visible"
        for media, declarations in (
            ("min-width: 1000px", {"max-height": "440px", "overflow-y": "auto",
                "overflow-x": "hidden", "overscroll-behavior": "contain", "scrollbar-gutter": "stable"}),
            ("max-width: 999px", {"max-height": "none", "overflow-y": "visible",
                "overflow-x": "clip", "scrollbar-gutter": "auto"}),
        ):
            rule = re.search(r'@media screen and \(' + re.escape(media)
                             + r'\)\s*\{\s*' + re.escape(selector) + r'\s*\{([^}]+)\}', css)
            self.assertIsNotNone(rule, media)
            actual = dict(re.findall(r'([\w-]+)\s*:\s*([^;]+);', rule.group(1)))
            for name, value in declarations.items():
                self.assertEqual(actual.get(name), value, (media, name))
        scrollbar = re.search(re.escape(selector) + r'\s*\{([^}]+)\}', css).group(1)
        self.assertIn("scrollbar-width: thin;", scrollbar)
        self.assertIn("scrollbar-color: var(--poll-detail-line-strong) transparent;", scrollbar)
        self.assertRegex(css, re.escape(selector) + r'::-webkit-scrollbar\s*\{\s*width: 5px;')
        self.assertRegex(css, re.escape(selector) + r'::-webkit-scrollbar-thumb\s*\{\s*border-radius: 999px;')

    def test_hub_comparison_panels_share_accessible_title_info_component(self):
        for path in ("agenda/index.html", "en/agenda/index.html", "agenda/historique/index.html", "en/agenda/history/index.html"):
            text = self.text(path)
            for anchor in ("agenda-movement", "agenda-composition"):
                section = text.split(f'aria-labelledby="{anchor}-title"', 1)[1].split("</section>", 1)[0]
                for component in ("polling-title-row", "polling-title-info-wrap", "polling-title-info", "polling-title-tooltip"):
                    self.assertIn(f'class="{component}"', section)
                self.assertIn(f'aria-describedby="{anchor}-note"', section)
                self.assertIn(f'id="{anchor}-note" role="tooltip"', section)
                self.assertNotIn("agenda-note-tooltip", section)
            self.assertIn("source-days assigned to all agenda topics" if path.startswith("en/") else "jours-sources affectés à tous les thèmes", text)

    def test_bilingual_page_hierarchy_is_parallel(self):
        pairs = [("/agenda/", "/en/agenda/"), ("/agenda/historique/", "/en/agenda/history/")]
        for topic in self.projection["topics"]:
            pairs.extend([(topic["routes"]["fr"], topic["routes"]["en"]),
                          (topic["routes"]["history_fr"], topic["routes"]["history_en"])])
        for fr, en in pairs:
            documents = [self.text(Path(route.strip("/")) / "index.html") for route in (fr, en)]
            structures = []
            for document in documents:
                start = document.index('<nav class="poll-detail-breadcrumb"' if 'agenda-detail-page' in document else '<nav class="polling-breadcrumb"')
                end = document.index('fr27-app-hud', start)
                structures.append(ProductHierarchy(document[start:end]).roles)
            self.assertEqual(*structures, fr)

    def test_product_labels_do_not_import_incompatible_issue_semantics(self):
        for path in self.artifacts:
            text = self.text(path)
            labels = re.findall(r'<(?:h[12]|div|span|button)\b[^>]*>([^<>]*)</(?:h[12]|div|span|button)>', text)
            for label in labels:
                self.assertNotRegex(label.upper(), r'INCIDENCE|SOUS-THÈMES|SUBTOPICS|MULTI-LABEL|MULTI-ÉTIQUETTES')
            self.assertIn('SOURCE-DAYS' if str(path).startswith('en') else 'JOURS-SOURCES', text)
            self.assertIn('AGENDA SHARE' if str(path).startswith('en') else 'PART AGENDA', text)
            if "agenda-current-candidates" in text:
                section = text.split('agenda-current-candidates', 1)[1].split('</section>', 1)[0]
                title = re.search(r'<h2[^>]*>(.*?)</h2>', section).group(1)
                self.assertNotRegex(title.upper(), r'ENDORSEMENT|SUPPORT|SOUTIEN|PRIORIT|POSITION')
                self.assertIn('do not describe endorsement' if str(path).startswith('en') else 'ni soutien', section)

    def test_current_detail_required_structure_and_no_related_module(self):
        for topic in self.projection["topics"]:
            for language in ("fr", "en"):
                path = Path(topic["routes"][language].strip("/")) / "index.html"
                text = self.artifacts[path].decode("utf-8")
                markers = (
                    "poll-detail-breadcrumb",
                    "agenda-detail-hero",
                    "agenda-current-kpis",
                    "agenda-current-activity",
                    "agenda-current-comparison",
                    "agenda-subtopics",
                    "agenda-current-candidates",
                    "agenda-current-evidence",
                    "agenda-compact-history",
                    "agenda-detail-crosslinks",
                    "fr27-app-hud",
                )
                positions = [text.index(marker) for marker in markers]
                self.assertEqual(positions, sorted(positions))
                self.assertNotIn("agenda-related", text)
                self.assertNotIn("EVIDENCE INTERSECTION", text)
                self.assertNotIn("INTERSECTION DE PREUVES", text)

    def test_history_hub_required_structure(self):
        for relative in ("agenda/historique/index.html", "en/agenda/history/index.html"):
            text = self.text(relative)
            markers = (
                "polling-breadcrumb",
                "polling-intro agenda-intro",
                "polling-metrics agenda-metrics",
                "agenda-landscape-panel",
                "agenda-movement-panel",
                "agenda-agenda-panel",
                "agenda-history-gateway",
                "fr27-app-hud",
            )
            self.assertEqual(
                [text.index(marker) for marker in markers],
                sorted(text.index(marker) for marker in markers),
            )

    def test_historical_candidate_adaptive_columns_preserve_order_and_global_scale(self):
        candidates = max((topic["historical_candidate_associations"]["candidates"]
                          for topic in self.projection["topics"]), key=len)
        self.assertGreaterEqual(len(candidates), 22)
        for language in ("fr", "en"):
            for size in (0, 1, 6, 7, 21, 22):
                with self.subTest(language=language, size=size):
                    data = {"candidates": copy.deepcopy(candidates[:size])}
                    original = copy.deepcopy(data)
                    rendered = builder._candidate_columns(data, language, historical=True)
                    self.assertEqual(rendered, builder._candidate_columns(data, language, historical=True))
                    self.assertEqual(data, original)
                    columns = re.findall(r'<ul class="agenda-history-candidate-column"[^>]*>(.*?)</ul>', rendered)
                    expected = [] if not size else [size] if size <= 6 else [(size + 1) // 2, size // 2]
                    self.assertEqual([column.count("<li>") for column in columns], expected)
                    if size:
                        self.assertIn("is-single" if size <= 6 else "is-split", rendered)
                        maximum = max(candidate["association_count"] for candidate in data["candidates"])
                        values = [float(value) for value in re.findall(r'--agenda-history-candidate-share:([\d.]+)', rendered)]
                        self.assertEqual(values, [round(candidate["association_count"] / maximum, 6)
                                                  for candidate in data["candidates"]])
                        self.assertEqual(re.findall(r'<strong>(\d+) associations?</strong>', rendered),
                                         [str(candidate["association_count"]) for candidate in data["candidates"]])
                        for column, group in zip(columns, [data["candidates"]] if size <= 6 else
                                                 [data["candidates"][:(size + 1) // 2], data["candidates"][(size + 1) // 2:]]):
                            names = [builder._h(candidate["candidate_name"]) for candidate in group]
                            self.assertEqual([column.index(name) for name in names], sorted(column.index(name) for name in names))
                            for candidate in group:
                                self.assertIn(builder._h(builder._period(candidate["first_association"], candidate["last_association"], language)), column)
                                self.assertIn(f'{candidate["observed_days"]} ' + (("jour" if candidate["observed_days"] == 1 else "jours") if language == "fr" else ("day" if candidate["observed_days"] == 1 else "days")), column)

    def test_historical_detail_hero_uses_source_day_peak_and_observation_dates(self):
        for topic in self.projection["topics"]:
            history = topic["coverage_history"]
            peak = max(point["source_day_count"] for point in history["daily"])
            for language, key in (("fr", "history_fr"), ("en", "history_en")):
                text = self.artifacts[Path(topic["routes"][key].strip("/")) / "index.html"].decode("utf-8")
                hero = text.split('<section class="poll-detail-hero agenda-detail-hero">', 1)[1].split("</section>", 1)[0]
                labels = ["JOURS-SOURCES · HIST.", "JOURS ACTIFS", "PIC JOURNALIER", "PREMIÈRE OBS.", "DERNIÈRE OBS."] if language == "fr" else ["SOURCE-DAYS · HISTORY", "ACTIVE DAYS", "DAILY PEAK", "FIRST OBS.", "LATEST OBS."]
                self.assertEqual(re.findall(r'<div class="poll-detail-metric(?: poll-detail-metric-fieldwork)?"><span>([^<]+)</span><strong>([^<]+)</strong></div>', hero),
                                 list(zip(labels, [str(history["total_source_days"]), str(history["active_days"]), str(peak),
                                                  builder._date(history["first_observation"], language), builder._date(history["last_observation"], language)])))
                for removed in ("ARTICLES CLASSÉS", "CLASSIFIED ITEMS", "MAX GLISSANT · 30 J", "MAX ROLLING · 30D"):
                    self.assertNotIn(removed, hero)
                self.assertIn("total_items", history)
                self.assertIn("maximum_rolling_30d_source_days", history)

    def test_historical_detail_candidate_panels_use_adaptive_helper(self):
        for topic in self.projection["topics"]:
            for language, key in (("fr", "history_fr"), ("en", "history_en")):
                text = self.artifacts[Path(topic["routes"][key].strip("/")) / "index.html"].decode("utf-8")
                expected = builder._candidate_columns(topic["historical_candidate_associations"], language, historical=True)
                self.assertIn(expected, text)
                panel = text.split('agenda-history-peaks">', 1)[1].split("</aside>", 1)[0]
                peak_count = min(5, sum(bool(point["item_count"]) for point in topic["coverage_history"]["daily"]))
                self.assertIn(f'<span class="poll-detail-panel-status">{peak_count} {"JOURS" if language == "fr" else "DAYS"}</span>', panel)
                self.assertIn('<div class="agenda-history-peak-unit">' + ("JOURS-SOURCES" if language == "fr" else "SOURCE-DAYS") + "</div>", panel)

    def test_historical_longitudinal_title_uses_accessible_tooltip_only_methodology(self):
        for topic in self.projection["topics"]:
            for language, key in (("fr", "history_fr"), ("en", "history_en")):
                text = self.artifacts[Path(topic["routes"][key].strip("/")) / "index.html"].decode("utf-8")
                panel = text.split('agenda-history-detail-evolution">', 1)[1].split("</section>", 1)[0]
                expected = (
                    "Les barres représentent les jours-sources observés par jour. "
                    "« Part agenda » rapporte le thème à l’ensemble des thèmes classés de l’agenda."
                    if language == "fr" else
                    "Bars represent observed source-days per day. "
                    "“Agenda share” measures the topic against all classified Agenda topics."
                )
                self.assertIn('<div class="agenda-note-title-line"><h2 id="agenda-history-coverage-title">', panel)
                self.assertIn('aria-describedby="agenda-history-coverage-note"', panel)
                self.assertIn('id="agenda-history-coverage-note" role="tooltip">' + builder._h(expected), panel)
                self.assertEqual(panel.count(builder._h(expected)), 1)
                self.assertIn('aria-label="' + ("Note méthodologique" if language == "fr" else "Method note") + '"', panel)
                self.assertEqual(panel.count('class="agenda-history-detail-bar"'), len(topic["coverage_history"]["daily"]))

    def test_historical_candidate_css_matches_bounded_issues_behavior(self):
        css = (ROOT / "assets/agenda.css").read_text(encoding="utf-8")
        self.assertRegex(css, r'\.agenda-history-detail-page \.agenda-history-candidate-ledgers\.is-single\s*\{\s*grid-template-columns: minmax\(0, 1fr\);')
        desktop = css[css.index("@media screen and (min-width: 1000px)", css.index(".agenda-history-candidate-ledgers")):]
        rule = re.search(r'\.agenda-history-detail-page \.agenda-history-candidate-column\s*\{([^}]+)\}', desktop).group(1)
        for declaration in ("max-height: 206px;", "overflow-y: auto;", "overscroll-behavior: contain;", "scrollbar-gutter: stable;"):
            self.assertIn(declaration, rule)
        mobile = desktop.split("@media screen and (max-width: 999px)", 1)[1]
        self.assertIn(".agenda-history-candidate-ledgers {\n    grid-template-columns: minmax(0, 1fr);", mobile)
        rule = re.search(r'\.agenda-history-detail-page \.agenda-history-candidate-column,\s*\.agenda-history-detail-page \.agenda-history-daily-ledger\s*\{([^}]+)\}', mobile).group(1)
        for declaration in ("max-height: none;", "overflow-y: visible;", "scrollbar-gutter: auto;"):
            self.assertIn(declaration, rule)

    def test_historical_candidate_rendering_is_isolated_from_locked_families(self):
        original = builder._candidate_columns
        def historical_only(data, language, *, historical=False):
            return "<div>historical candidate sentinel</div>" if historical else original(data, language)
        projection_before = copy.deepcopy(self.projection)
        with patch.object(builder, "_candidate_columns", side_effect=historical_only):
            rebuilt = builder.build_from_paths(write=False)["artifacts"]
        history_details = {Path(topic["routes"][key].strip("/")) / "index.html"
                           for topic in self.projection["topics"] for key in ("history_fr", "history_en")}
        for path, original_bytes in self.artifacts.items():
            if path not in history_details:
                self.assertEqual(rebuilt[path], original_bytes, path)
        self.assertEqual(self.projection, projection_before)

    def test_history_detail_required_structure(self):
        for topic in self.projection["topics"]:
            for language, key in (("fr", "history_fr"), ("en", "history_en")):
                path = Path(topic["routes"][key].strip("/")) / "index.html"
                text = self.artifacts[path].decode("utf-8")
                markers = (
                    "poll-detail-breadcrumb",
                    "agenda-detail-hero",
                    "agenda-history-detail-evolution",
                    "agenda-history-peaks",
                    "agenda-history-candidates",
                    "agenda-history-daily",
                    "agenda-history-detail-actions",
                    "fr27-app-hud",
                )
                self.assertEqual(
                    [text.index(marker) for marker in markers],
                    sorted(text.index(marker) for marker in markers),
                )

    def history_details(self):
        for topic in self.projection["topics"]:
            for language, key in (("fr", "history_fr"), ("en", "history_en")):
                path = Path(topic["routes"][key].strip("/")) / "index.html"
                yield topic, language, path, self.text(path)

    def test_history_detail_structural_language_contract(self):
        labels = {
            "fr": ("THÈME · HISTORIQUE", "JOURS-SOURCES · HIST.", "JOURS ACTIFS", "PIC JOURNALIER",
                   "PREMIÈRE OBS.", "DERNIÈRE OBS.", "LONGITUDINAL", "HISTORIQUE DE LA COUVERTURE",
                   "JOURS-SOURCES", "PART AGENDA", "REPÈRES", "JOURS MARQUANTS",
                   "DOMAINE SÉPARÉ", "HISTORIQUE DES ASSOCIATIONS CANDIDAT × THÈME", "DONNÉES",
                   "REGISTRE JOUR PAR JOUR", "VOIR L’ÉTAT ACTUEL", "TOUT L’HISTORIQUE DE L’AGENDA"),
            "en": ("TOPIC · HISTORY", "SOURCE-DAYS · HISTORY", "ACTIVE DAYS", "DAILY PEAK",
                   "FIRST OBS.", "LATEST OBS.", "LONGITUDINAL", "COVERAGE HISTORY", "SOURCE-DAYS",
                   "AGENDA SHARE", "HIGHLIGHTS", "PEAK DAYS", "SEPARATE DOMAIN",
                   "CANDIDATE × TOPIC ASSOCIATION HISTORY", "DATA", "DAY-BY-DAY LEDGER",
                   "VIEW CURRENT STATE", "ALL AGENDA HISTORY"),
        }
        for _, language, path, text in self.history_details():
            with self.subTest(path=path):
                copy = "\n".join(ProductCopy(text).copy)
                for label in labels[language]:
                    self.assertIn(label, copy)
                self.assertEqual(language_leaks(text, language), [])
                self.assertNotIn("LAST OBS.", copy)
                self.assertNotRegex(copy, r"\b1 (?:associations|jours|days|articles|items)\b")

    def test_history_detail_complete_day_domain_and_every_ledger_cell(self):
        period = self.coverage["period"]
        # The historical start is contract-locked, while the end advances
        # to the latest complete UTC day represented by the artifact.
        start_day = date.fromisoformat(period["start_date"])
        data_as_of_day = date.fromisoformat(self.coverage["data_as_of"][:10])
        expected_end = data_as_of_day - timedelta(days=1)
        expected_days = (expected_end - start_day).days + 1

        self.assertEqual(period["start_date"], "2026-07-23")
        self.assertEqual(period["end_date"], expected_end.isoformat())
        self.assertEqual(period["days"], expected_days)
        self.assertEqual(period["days"], len(self.coverage["daily"]))
        self.assertTrue(period["current_utc_day_excluded"])
        self.assertLess(period["end_date"], self.coverage["data_as_of"][:10])
        dates = [(date.fromisoformat(period["start_date"]) + timedelta(days=i)).isoformat()
                 for i in range(period["days"])]
        denominators = {point["date"]: point for point in self.coverage["daily"]}
        source_topics = {topic["id"]: topic for topic in self.coverage["topics"]}
        for topic, language, path, text in self.history_details():
            source = source_topics[topic["topic_id"]]
            daily = source["daily"]
            active = [point for point in daily if point["source_day_count"] > 0]
            with self.subTest(path=path):
                self.assertEqual([point["date"] for point in daily], dates)
                self.assertEqual(source["total_source_days"], sum(point["source_day_count"] for point in daily))
                self.assertEqual(source["active_days"], len(active))
                self.assertLessEqual(len(active), period["days"])
                self.assertEqual(source["first_observation"], active[0]["date"])
                self.assertEqual(source["last_observation"], active[-1]["date"])
                chart = re.findall(r'class="agenda-history-detail-bar" title="([^"]+)"', text)
                self.assertEqual(len(chart), period["days"])
                rows = re.findall(r'<tr>(<td .*?)</tr>', text)
                self.assertEqual(len(rows), period["days"])
                for point, row, bar in zip(daily, rows, chart):
                    denominator = denominators[point["date"]]
                    total_sources = denominator["total_agenda_topic_source_days"]
                    share = point["source_day_count"] / total_sources if total_sources else 0.0
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row)
                    self.assertEqual(re.findall(r'datetime="([^"]+)"', cells[0]), [point["date"]])
                    self.assertEqual(cells[1:], [str(point["item_count"]), str(point["source_day_count"]),
                                                str(denominator["total_classified_agenda_items"]), str(total_sources),
                                                builder._decimal(share * 100, language, 2) + "%"])
                    self.assertAlmostEqual(point["topic_source_day_share"], share)
                    self.assertIn(builder._date(point["date"], language), bar)
                    self.assertIn(f' · {point["source_day_count"]} · ', bar)

    def test_history_detail_all_peak_rows_reconcile_with_authoritative_order(self):
        source_topics = {topic["id"]: topic for topic in self.coverage["topics"]}
        for topic, language, path, text in self.history_details():
            daily = source_topics[topic["topic_id"]]["daily"]
            expected = sorted((point for point in daily if point["item_count"]),
                              key=lambda p: (-p["source_day_count"], -p["item_count"], p["date"]))[:5]
            rows = re.findall(r'<li data-peak-day="([^"]+)">(.*?)</li>', text)
            with self.subTest(path=path):
                self.assertEqual([day for day, _ in rows], [p["date"] for p in expected])
                for (_, row), point in zip(rows, expected):
                    self.assertIn(f'<strong>{point["source_day_count"]}</strong>', row)
                    unit = ("article" if point["item_count"] == 1 else "articles") if language == "fr" else ("item" if point["item_count"] == 1 else "items")
                    self.assertIn(f'{point["item_count"]} {unit} · ' + builder._decimal(point["topic_source_day_share"] * 100, language, 2) + "%", row)
                    self.assertIn(f'--agenda-history-peak-share:{point["source_day_count"] / expected[0]["source_day_count"]:.6f}', row)

    def test_history_detail_candidates_reconcile_with_raw_retained_associations(self):
        period = self.coverage["period"]
        for topic, language, path, text in self.history_details():
            expected = []
            for candidate in self.candidate_history["candidates"]:
                observations = [(point["date"], point["campaign_counts"][topic["topic_id"]])
                                for point in candidate["daily_series"]
                                if period["start_date"] <= point["date"] <= period["end_date"]
                                and point["campaign_counts"][topic["topic_id"]] > 0]
                if observations:
                    expected.append((sum(count for _, count in observations), candidate["candidate_name"],
                                     candidate["candidate_id"], observations[0][0], observations[-1][0], len(observations)))
            expected.sort(key=lambda p: (-p[0], p[1].casefold(), p[2]))
            actual = topic["historical_candidate_associations"]["candidates"]
            with self.subTest(path=path):
                self.assertEqual([(c["association_count"], c["candidate_name"], c["candidate_id"],
                                   c["first_association"], c["last_association"], c["observed_days"]) for c in actual], expected)
                rows = re.findall(r'<li>(<div class="agenda-history-candidate-primary">.*?)</li>', text)
                self.assertEqual(len(rows), len(expected))
                maximum = max((p[0] for p in expected), default=1)
                for row, (count, name, _, first, latest, days) in zip(rows, expected):
                    self.assertIn(builder._h(name), row)
                    self.assertIn(f'<strong>{count} {"association" if count == 1 else "associations"}</strong>', row)
                    self.assertIn(builder._h(builder._period(first, latest, language)), row)
                    unit = ("jour" if days == 1 else "jours") if language == "fr" else ("day" if days == 1 else "days")
                    self.assertIn(f' · {days} {unit}</span>', row)
                    self.assertIn(f'--agenda-history-candidate-share:{count / maximum:.6f}', row)

    def test_history_detail_markup_accessible_regions_and_keyboard_scroll_targets(self):
        for _, language, path, text in self.history_details():
            markup = HistoricalMarkup(text)
            ids = [attrs["id"] for _, attrs in markup.elements if "id" in attrs]
            with self.subTest(path=path):
                self.assertEqual(markup.errors, [])
                self.assertEqual(len(ids), len(set(ids)))
                for tag, attrs in markup.elements:
                    for attribute in ("aria-labelledby", "aria-describedby"):
                        for identifier in attrs.get(attribute, "").split():
                            self.assertIn(identifier, ids)
                    if "data-history-mode" in attrs:
                        self.assertEqual(tag, "button")
                        self.assertEqual(attrs["type"], "button")
                        self.assertIn(attrs["aria-pressed"], ("true", "false"))
                    if attrs.get("class") in ("agenda-history-candidate-column", "agenda-history-table-wrap agenda-history-daily-ledger"):
                        self.assertEqual(attrs["tabindex"], "0")
                        self.assertTrue(attrs.get("aria-labelledby"))
                nav = next(attrs for tag, attrs in markup.elements if attrs.get("class") == "poll-detail-breadcrumb")
                self.assertEqual(nav["aria-label"], "Fil d’Ariane" if language == "fr" else "Breadcrumb")
                self.assertEqual(sum(tag == "h1" for tag, _ in markup.elements), 1)
                self.assertNotRegex(text, r'\b(?:None|NaN|undefined|null)\b')

    def test_history_sparse_viewport_and_keyboard_focus_css_are_scoped(self):
        css = (ROOT / "assets/agenda.css").read_text(encoding="utf-8")
        rule = re.search(r'\.agenda-history-detail-page \.agenda-history-candidate-ledgers\.is-single\s+\.agenda-history-candidate-column\s*\{([^}]+)\}', css).group(1)
        for declaration in ("max-height: none;", "overflow-y: visible;", "scrollbar-gutter: auto;"):
            self.assertIn(declaration, rule)
        self.assertIn(".agenda-history-detail-page .agenda-history-candidate-column:focus-visible", css)
        self.assertIn(".agenda-history-detail-page .agenda-history-daily-ledger:focus-visible", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn(".agenda-history-detail-page .agenda-note-tooltip.is-dismissed", css)
        script = (ROOT / "assets/agenda.js").read_text(encoding="utf-8")
        self.assertIn('".agenda-history-detail-page .agenda-note-tooltip"', script)
        self.assertIn('event.key === "Escape"', script)
        self.assertIn("event.stopPropagation()", script)

    def test_history_detail_changes_cannot_change_locked_generated_families(self):
        history_paths = {path for _, _, path, _ in self.history_details()}
        # Checked-in publication may predate refreshed source data. Isolation
        # requires identical renders and untouched files, not artifact freshness.
        checked_in = {path: (ROOT / path).read_bytes() for path in self.artifacts}
        with patch.object(builder, "_history_detail", return_value=b"historical detail sentinel"):
            rebuilt = builder.build_from_paths(write=False)["artifacts"]
        for path, content in self.artifacts.items():
            if path not in history_paths:
                self.assertEqual(rebuilt[path], content, path)
                self.assertEqual(
                    normalized((ROOT / path).read_bytes()),
                    normalized(checked_in[path]),
                    path,
                )

    def test_reciprocal_hreflang_french_default_and_unique_canonicals(self):
        seen = set()
        for relative, content in self.artifacts.items():
            text = content.decode("utf-8")
            own = canonical(text)
            fr = alternate(text, "fr")
            en = alternate(text, "en")
            self.assertEqual(alternate(text, "x-default"), fr)
            self.assertIn(own, {fr, en})
            self.assertNotIn(own, seen)
            seen.add(own)
            counterpart_route = urlparse(en if own == fr else fr).path.strip("/")
            counterpart = Path(counterpart_route) / "index.html"
            counterpart_text = self.artifacts[counterpart].decode("utf-8")
            self.assertEqual(alternate(counterpart_text, "fr"), fr)
            self.assertEqual(alternate(counterpart_text, "en"), en)

    def test_localized_metadata_open_graph_and_twitter(self):
        for relative, content in self.artifacts.items():
            text = content.decode("utf-8")
            language = "en" if str(relative).replace("\\", "/").startswith("en/") else "fr"
            self.assertRegex(text, r"<title>[^<]+</title>")
            self.assertRegex(text, r'<meta name="description" content="[^"]+">')
            self.assertIn('<meta property="og:url" content="', text)
            self.assertIn('<meta property="og:title" content="', text)
            self.assertIn('<meta property="og:description" content="', text)
            self.assertIn(f'<meta property="og:locale" content="{"en_GB" if language == "en" else "fr_FR"}">', text)
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', text)
            self.assertIn('<meta name="twitter:title" content="', text)
            self.assertIn('<meta name="twitter:description" content="', text)
            self.assertIn('/assets/og-cover.png', text)

    def test_hubs_have_collection_itemlist_and_all_pages_have_breadcrumb_jsonld(self):
        for relative, content in self.artifacts.items():
            text = content.decode("utf-8")
            self.assertIn('"@type":"BreadcrumbList"', text)
            is_hub = relative in {
                Path("agenda/index.html"),
                Path("en/agenda/index.html"),
                Path("agenda/historique/index.html"),
                Path("en/agenda/history/index.html"),
            }
            self.assertEqual('"@type":"CollectionPage"' in text, is_hub)
            if is_hub:
                self.assertIn('"@type":"ItemList"', text)
                self.assertIn('"numberOfItems":6', text)

    def test_no_null_leakage_malformed_internal_urls_or_issue_markup(self):
        for relative, content in self.artifacts.items():
            text = content.decode("utf-8")
            self.assertNotIn("None", text)
            self.assertNotIn(">null<", text)
            self.assertNotRegex(text, r'href="(?:|None|null|undefined)"')
            self.assertNotIn("issues.css", text)
            self.assertNotIn("issues.js", text)
            self.assertNotRegex(text, r'class="[^"]*\bissue-')
            for url in re.findall(r'(?:href|content)="(https?://[^"]+)"', text):
                parsed = urlparse(html_unescape(url))
                self.assertTrue(parsed.scheme and parsed.netloc, (relative, url))

    def test_renderers_and_repeated_full_build_are_deterministic(self):
        second = builder.build_from_paths(write=False)
        self.assertEqual(self.manifest, second["manifest"])
        self.assertEqual(set(self.artifacts), set(second["artifacts"]))
        for path in self.artifacts:
            self.assertEqual(normalized(self.artifacts[path]), normalized(second["artifacts"][path]))
        self.assertEqual(
            self.artifacts[Path("agenda/index.html")],
            builder._hub_common(
                self.projection,
                language="fr",
                shell=builder.load_shell_templates(ROOT)["fr"] | {
                    "footer": builder.prepare_footer(
                        builder.load_shell_templates(ROOT)["fr"]["footer"],
                        json.loads((ROOT / "poll_pages_manifest.json").read_text(encoding="utf-8"))["wave_count"],
                    )
                },
                favicon=builder._site_favicon_link(ROOT),
                og_image=builder._site_og_image_url(ROOT),
                history=False,
            ),
        )

    def test_check_detects_stale_text_with_normalized_portable_comparison(self):
        relative = Path(f".agenda-page-stale-{uuid.uuid4().hex}.html")
        target = ROOT / relative
        self.addCleanup(target.unlink, missing_ok=True)
        target.write_text("stale\n", encoding="utf-8")
        fake = {"artifacts": {relative: b"expected\n"}, "manifest": self.manifest}
        with (
            patch.object(builder, "build_from_paths", return_value=fake),
            patch.object(builder, "_generated_files", return_value={relative}),
            patch.object(builder, "serialize_manifest", return_value=(ROOT / "agenda_pages_manifest.json").read_bytes()),
        ):
            errors = builder.check_from_paths(root=ROOT, manifest_path=ROOT / "agenda_pages_manifest.json")
        self.assertIn(f"out of date: {relative.as_posix()}", errors)
        self.assertTrue(builder._same_text_bytes(b"same\r\n", b"same\n"))

    def test_thin_page_audit_is_clean(self):
        self.assertEqual(builder.thin_page_audit(self.result, ROOT), [])

    def test_all_six_topics_are_current_and_rendered(self):
        self.assertEqual(
            [topic["topic_id"] for topic in self.projection["topics"]],
            [definition.topic_id for definition in AGENDA_DEFINITIONS],
        )
        self.assertTrue(all(topic["lifecycle"] == "current" for topic in self.projection["topics"]))
        self.assertTrue(all(topic["qualification"]["current"] for topic in self.projection["topics"]))

    def test_dormant_sparse_state_and_unpublished_manifest_exclusion(self):
        topic = copy.deepcopy(self.projection["topics"][0])
        topic["lifecycle"] = "dormant"
        topic["qualification"] = {
            "current": False,
            "historical": False,
            "retained_previously_public": True,
        }
        shell = builder.load_shell_templates(ROOT)["en"]
        wave_count = json.loads((ROOT / "poll_pages_manifest.json").read_text(encoding="utf-8"))["wave_count"]
        shell["footer"] = builder.prepare_footer(shell["footer"], wave_count)
        rendered = builder._current_detail(
            self.projection,
            topic,
            language="en",
            shell=shell,
            favicon=builder._site_favicon_link(ROOT),
            og_image=builder._site_og_image_url(ROOT),
        ).decode("utf-8")
        self.assertIn("current activity is below the display threshold", rendered)
        self.assertIn("is-dormant", rendered)

        phase_one = project_agenda_pages(self.news, self.coverage, candidate_history=self.candidate_history)
        phase_one["topics"][0]["public"] = False
        manifest = agenda_manifest_payload(phase_one)
        self.assertEqual(manifest["public_topic_count"], 5)
        self.assertNotIn(
            phase_one["topics"][0]["topic_id"],
            {page["topic_id"] for page in manifest["pages"]},
        )

    def test_no_policy_taxonomy_or_unknown_topic_enters_family(self):
        self.assertFalse(
            {topic["topic_id"] for topic in self.projection["topics"]}
            & POLICY_AGENDA_IDS
        )
        self.assertFalse(
            {page["topic_id"] for page in self.manifest["pages"]} & POLICY_AGENDA_IDS
        )

    def test_associated_signals_come_only_from_matched_term_counts(self):
        for topic in self.projection["topics"]:
            path = Path(topic["routes"]["en"].strip("/")) / "index.html"
            text = self.artifacts[path].decode("utf-8")
            self.assertIn("ASSOCIATED SIGNALS", text)
            signals = topic["current_evolution_projection"]["matched_term_counts"]
            for signal in signals:
                self.assertIn(_escaped(signal["term"]), text)
            self.assertNotIn("OBSERVED SUBTOPICS", text)

    def test_candidate_associations_are_semantically_and_numerically_separate(self):
        for topic in self.projection["topics"]:
            current_path = Path(topic["routes"]["en"].strip("/")) / "index.html"
            history_path = Path(topic["routes"]["history_en"].strip("/")) / "index.html"
            current_text = self.artifacts[current_path].decode("utf-8")
            history_text = self.artifacts[history_path].decode("utf-8")
            self.assertIn("do not describe endorsement, position, priority, or commitment", current_text)
            self.assertIn("separate from media volumes", history_text)
            self.assertEqual(
                topic["historical_candidate_associations"]["association_count"],
                sum(
                    candidate["association_count"]
                    for candidate in topic["historical_candidate_associations"]["candidates"]
                ),
            )

    def test_current_evidence_uses_base_cap_omissions_and_verbatim_urls(self):
        source = {
            topic["id"]: topic for topic in self.news["campaign_agenda"]["topics"]
        }
        for topic in self.projection["topics"]:
            base = source[topic["topic_id"]]
            current = topic["current"]
            self.assertEqual(current["supporting_item_count"], base["supporting_item_count"])
            self.assertEqual(current["omitted_item_count"], base["omitted_item_count"])
            self.assertEqual(current["supporting_items"], base["supporting_items"])
            for language in ("fr", "en"):
                path = Path(topic["routes"][language].strip("/")) / "index.html"
                text = self.text(path)
                section = text.split('agenda-published-evidence agenda-current-evidence', 1)[1].split('</section>', 1)[0]
                rows = re.findall(r'<article class="agenda-evidence-row">(.*?)</article>', section)
                self.assertEqual(len(rows), base["supporting_item_count"])
                self.assertLessEqual(len(rows), 20)
                # Exact source URL sequence locks every row's deterministic order.
                urls = [html_unescape(re.search(r'<a href="([^"]+)"', row).group(1)) for row in rows]
                self.assertEqual(urls, [item["url"] for item in base["supporting_items"]])
                for row, item in zip(rows, base["supporting_items"]):
                    self.assertIn(f'<h3>{_escaped(item["headline"])}</h3>', row)
                    self.assertIn(f'<strong>{_escaped(item["publisher"])}</strong>', row)
                published, omitted = ("PUBLIÉES", "OMISES") if language == "fr" else ("PUBLISHED", "OMITTED")
                self.assertIn(f'{base["supporting_item_count"]} {published} · {base["omitted_item_count"]} {omitted}', section)

    def test_complete_week_movement_uses_exact_evolution_domain(self):
        source = {
            topic["id"]: topic
            for topic in self.news["campaign_agenda"]["evolution"]["topics"]
        }
        period = self.news["campaign_agenda"]["evolution"]
        for topic in self.projection["topics"]:
            comparison = topic["current"]["comparison"]
            canonical_topic = source[topic["topic_id"]]
            self.assertEqual(
                comparison["latest_source_day_count"],
                sum(
                    point["source_day_count"]
                    for point in canonical_topic["daily_activity"]
                    if period["latest_start"] <= point["date"] <= period["latest_end"]
                ),
            )
            self.assertEqual(topic["current"]["item_count"], canonical_topic["item_count"])

    def test_historical_metrics_are_from_topic_coverage_history(self):
        source = {topic["id"]: topic for topic in self.coverage["topics"]}
        for topic in self.projection["topics"]:
            self.assertEqual(topic["coverage_history"], source[topic["topic_id"]])
            path = Path(topic["routes"]["history_en"].strip("/")) / "index.html"
            text = self.artifacts[path].decode("utf-8")
            self.assertIn(f'<strong>{source[topic["topic_id"]]["total_source_days"]}</strong>', text)

    def test_persistent_history_excludes_current_partial_day(self):
        self.assertTrue(self.coverage["period"]["current_utc_day_excluded"])
        self.assertLess(
            self.coverage["period"]["end_date"], self.coverage["data_as_of"][:10]
        )
        for topic in self.projection["topics"]:
            self.assertEqual(
                topic["coverage_history"]["daily"][-1]["date"],
                self.coverage["period"]["end_date"],
            )

    def test_peak_days_follow_locked_order(self):
        for topic in self.projection["topics"]:
            expected = sorted(
                [point for point in topic["coverage_history"]["daily"] if point["item_count"]],
                key=lambda point: (
                    -point["source_day_count"],
                    -point["item_count"],
                    point["date"],
                ),
            )[:5]
            path = Path(topic["routes"]["history_en"].strip("/")) / "index.html"
            text = self.artifacts[path].decode("utf-8")
            actual = re.findall(r'data-peak-day="([0-9-]+)"', text)
            self.assertEqual(actual, [point["date"] for point in expected])

    def test_daily_ledger_denominators_reconcile(self):
        for topic in self.projection["topics"]:
            for point in topic["coverage_history"]["daily"]:
                self.assertLessEqual(point["item_count"], point["total_classified_agenda_items"])
                self.assertLessEqual(
                    point["source_day_count"], point["total_agenda_topic_source_days"]
                )
                expected = (
                    point["source_day_count"] / point["total_agenda_topic_source_days"]
                    if point["total_agenda_topic_source_days"]
                    else 0.0
                )
                self.assertEqual(point["topic_source_day_share"], expected)

    def test_footer_hud_is_prepared_from_live_poll_manifest(self):
        wave_count = json.loads(
            (ROOT / "poll_pages_manifest.json").read_text(encoding="utf-8")
        )["wave_count"]
        for content in self.artifacts.values():
            text = content.decode("utf-8")
            self.assertIn('id="fr27-hud-polls-value"', text)
            self.assertIn(f'>{wave_count}</strong>', text)
        source = inspect.getsource(builder.build_from_paths)
        self.assertIn("prepare_footer", source)
        self.assertIn("poll_pages_manifest.json", source)

    def test_french_english_dom_hierarchy_is_parallel(self):
        pairs = [
            (Path("agenda/index.html"), Path("en/agenda/index.html")),
            (Path("agenda/historique/index.html"), Path("en/agenda/history/index.html")),
        ]
        for topic in self.projection["topics"]:
            pairs.extend(
                [
                    (
                        Path(topic["routes"]["fr"].strip("/")) / "index.html",
                        Path(topic["routes"]["en"].strip("/")) / "index.html",
                    ),
                    (
                        Path(topic["routes"]["history_fr"].strip("/")) / "index.html",
                        Path(topic["routes"]["history_en"].strip("/")) / "index.html",
                    ),
                ]
            )
        for french, english in pairs:
            fr_classes = re.findall(r'class="([^"]+)"', self.artifacts[french].decode("utf-8"))
            en_classes = re.findall(r'class="([^"]+)"', self.artifacts[english].decode("utf-8"))
            self.assertEqual(fr_classes, en_classes, (french, english))

    def test_css_preserves_issues_baseline_with_scoped_agenda_hub_overrides(self):
        source = (ROOT / "assets" / "issues.css").read_text(encoding="utf-8")
        expected = (
            source.replace("ISSUES", "AGENDA")
            .replace("Issues", "Agenda")
            .replace("issues", "agenda")
            .replace("ISSUE", "AGENDA")
            .replace("Issue", "Agenda")
            .replace("issue", "agenda")
        )
        actual = (ROOT / "assets" / "agenda.css").read_text(encoding="utf-8")
        actual_normalized = actual.replace("\r\n", "\n")
        expected_normalized = expected.replace("\r\n", "\n")

        self.assertTrue(
            actual_normalized.startswith(expected_normalized),
            "Agenda CSS must preserve the complete namespaced Issues visual baseline",
        )

        override = actual_normalized[len(expected_normalized):].lstrip("\n")

        self.assertTrue(
            override.startswith(
                "/* ==========================================================\n"
                "   FR27 AGENDA CURRENT HUB — MANUAL VISUAL PASS 01"
            ),
            "Agenda-specific CSS may only follow the locked Issues baseline",
        )

        self.assertEqual(
            override.count("FR27 AGENDA CURRENT HUB — MANUAL VISUAL PASS 01"),
            1,
        )

        self.assertNotIn(".issue-", override)

        self.assertNotIn(
            "CURRENT HUB COMPARISON — show all six topics, no nested scroll",
            override,
        )

        required_overrides = (
            ".agenda-hub-page .agenda-note-tooltip",
            ".agenda-hub-page .agenda-note-tooltip-body",
            ".agenda-hub-page:not(.agenda-history-page) .agenda-card-grid",
            "grid-template-columns: repeat(3, minmax(0, 1fr));",
        )

        for required in required_overrides:
            self.assertIn(required, override)

        self.assertIn("@media (min-width: 1100px)", override)
        self.assertIn("@media (min-width: 760px) and (max-width: 1099px)", override)
        self.assertIn("@media (max-width: 759px)", override)
        self.assertIn("@media", actual)
        self.assertIn("@media screen and (max-width: 479px)", actual)
        self.assertNotIn(".issue-", actual)

    def test_javascript_has_namespaced_search_sort_and_history_controls(self):
        script = (ROOT / "assets" / "agenda.js").read_text(encoding="utf-8")
        for hook in (
            "data-agenda-search",
            "data-agenda-card-grid",
            "data-agenda-sort",
            "data-history-panel",
            "data-history-mode",
        ):
            self.assertIn(hook, script)
        self.assertNotIn("data-issue", script)
        self.assertIn("AGENDA PERCENTAGE", script)

    def test_agenda_build_does_not_modify_issues_family(self):
        # Measure this builder's effects, independently of other authorized edits.
        protected = [ROOT / name for name in (
            "assets/issues.css", "assets/issues.js", "build_issue_pages.py", "issue_page_contract.py",
        )]
        protected += list((ROOT / "enjeux").rglob("*.*"))
        protected += list((ROOT / "en/issues").rglob("*.*"))
        before = {path: path.read_bytes() for path in protected}
        result = builder.build_from_paths(write=False)
        self.assertEqual({path: path.read_bytes() for path in protected}, before)
        self.assertFalse(any(str(path).replace("\\", "/").startswith(("enjeux/", "en/issues/"))
                             for path in result["artifacts"]))


def _escaped(value: str) -> str:
    import html

    return html.escape(value, quote=True)


def html_unescape(value: str) -> str:
    import html

    return html.unescape(value)


if __name__ == "__main__":
    unittest.main()
