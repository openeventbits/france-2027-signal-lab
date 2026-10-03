from __future__ import annotations

import copy
import inspect
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
            self.assertEqual(text.count(" data-agenda-card\n"), 6, relative)
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
                    "agenda-current-evidence",
                    "agenda-current-candidates",
                    "agenda-history-gateway",
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
                "agenda-latest",
                "agenda-history-gateway",
                "fr27-app-hud",
            )
            self.assertEqual(
                [text.index(marker) for marker in markers],
                sorted(text.index(marker) for marker in markers),
            )

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
            self.assertIn("ASSOCIATED CLASSIFIER SIGNALS", text)
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
            path = Path(topic["routes"]["en"].strip("/")) / "index.html"
            text = self.artifacts[path].decode("utf-8")
            for item in base["supporting_items"]:
                self.assertIn(_escaped(item["url"]), text)
            self.assertIn(f'{base["omitted_item_count"]} OMITTED', text)

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

        required_overrides = (
            ".agenda-hub-page .agenda-note-tooltip",
            ".agenda-hub-page .agenda-note-tooltip-body",
            ".agenda-hub-page:not(.agenda-history-page) .agenda-card-grid",
            "grid-template-columns: repeat(3, minmax(0, 1fr));",
            ".agenda-hub-page:not(.agenda-history-page)\n"
            "    .agenda-movement-panel",
            ".agenda-hub-page:not(.agenda-history-page)\n"
            "    .agenda-agenda-panel",
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
        output = subprocess.check_output(
            [
                "git",
                "diff",
                "--",
                "assets/issues.css",
                "assets/issues.js",
                "build_issue_pages.py",
                "issue_page_contract.py",
                "enjeux",
                "en/issues",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(output, "")
        self.assertFalse(any(str(path).replace("\\", "/").startswith("enjeux/") for path in self.artifacts))


def _escaped(value: str) -> str:
    import html

    return html.escape(value, quote=True)


def html_unescape(value: str) -> str:
    import html

    return html.unescape(value)


if __name__ == "__main__":
    unittest.main()
