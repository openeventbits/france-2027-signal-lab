"""Search-engine foundation and semantic-snapshot contracts for FR27."""

import copy
from contextlib import contextmanager
import html
import json
import os
from pathlib import Path
import re
import shutil
import unittest
from unittest import mock
import uuid
import xml.etree.ElementTree as ET

from build_search_entrypoints import (
    MAX_RECENT_CHANGES,
    RACE_END,
    RACE_START,
    WHAT_CHANGED_END,
    WHAT_CHANGED_START,
    SearchEntrypointError,
    build_documents,
    build_english_entrypoint,
    construct_semantic_model,
    generate_entrypoints,
    render_semantic_regions,
)


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
ENGLISH_INDEX = ROOT / "en" / "index.html"
ROBOTS = ROOT / "robots.txt"
SITEMAP = ROOT / "sitemap.xml"
CANDIDATE_SIGNALS = ROOT / "candidate_signals.json"
RECENT_CHANGES = ROOT / "recent_changes.json"

ROOT_URL = "https://france2027.app/"
ENGLISH_URL = "https://france2027.app/en/"

FRENCH_TITLE = "France 2027 Signal Lab — Signaux électoraux sourcés"
ENGLISH_TITLE = "France 2027 Signal Lab — Source-Linked Election Signals"

FRENCH_DESCRIPTION = (
    "Sondages sourcés, actualité électorale, couverture des candidats et "
    "vérifications pour la présidentielle française de 2027. "
    "Aucune moyenne, aucune prévision, aucun conseil de vote."
)
ENGLISH_DESCRIPTION = (
    "Source-linked polling, election news, candidate coverage and fact checks "
    "for France's 2027 presidential race. "
    "No averages, no forecast, no voting advice."
)


@contextmanager
def temporary_workspace():
    path = ROOT / f".test-search-foundation-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


class SearchFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_html = INDEX.read_text(encoding="utf-8")
        cls.english_html = ENGLISH_INDEX.read_text(encoding="utf-8")
        cls.candidate_signals = json.loads(
            CANDIDATE_SIGNALS.read_text(encoding="utf-8")
        )
        cls.recent_changes = json.loads(
            RECENT_CHANGES.read_text(encoding="utf-8")
        )

    @staticmethod
    def owned_region(text, start_marker, end_marker):
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker, start)
        return text[start:end]

    def test_root_is_static_french_canonical(self):
        self.assertIn(
            '<html lang="fr" data-site-root="./"',
            self.root_html,
        )
        self.assertNotIn('<base href="/">', self.root_html)
        self.assertIn(
            f'<link rel="canonical" href="{ROOT_URL}">',
            self.root_html,
        )
        self.assertIn(
            f'<meta property="og:url" content="{ROOT_URL}">',
            self.root_html,
        )
        self.assertIn(
            f"<title>{FRENCH_TITLE}</title>",
            self.root_html,
        )
        self.assertIn(
            f'<meta name="description" content="{FRENCH_DESCRIPTION}">',
            self.root_html,
        )

    def test_english_entrypoint_is_static_english_canonical(self):
        self.assertIn(
            '<html lang="en" data-site-root="/"',
            self.english_html,
        )
        self.assertEqual(
            self.english_html.count('<base href="/">'),
            1,
        )
        self.assertIn(
            f'<link rel="canonical" href="{ENGLISH_URL}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta property="og:url" content="{ENGLISH_URL}">',
            self.english_html,
        )
        self.assertIn(
            f"<title>{ENGLISH_TITLE}</title>",
            self.english_html,
        )
        self.assertIn(
            f'<meta name="description" content="{ENGLISH_DESCRIPTION}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta property="og:title" content="{ENGLISH_TITLE}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta property="og:description" content="{ENGLISH_DESCRIPTION}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta name="twitter:title" content="{ENGLISH_TITLE}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta name="twitter:description" content="{ENGLISH_DESCRIPTION}">',
            self.english_html,
        )

    def test_hreflang_cluster_is_reciprocal_and_identical(self):
        expected = (
            f'<link rel="alternate" hreflang="fr" href="{ROOT_URL}">',
            f'<link rel="alternate" hreflang="en" href="{ENGLISH_URL}">',
            f'<link rel="alternate" hreflang="x-default" href="{ROOT_URL}">',
        )
        for html in (self.root_html, self.english_html):
            for tag in expected:
                self.assertEqual(html.count(tag), 1)

    def test_static_language_links_use_canonical_routes(self):
        for html in (self.root_html, self.english_html):
            self.assertIn(
                '<a href="/" data-fr27-language="fr"',
                html,
            )
            self.assertIn(
                '<a href="/en/" data-fr27-language="en"',
                html,
            )
            self.assertNotIn('href="?lang=en"', html)

    def test_committed_english_entrypoint_is_deterministic(self):
        source = INDEX.read_text(encoding="utf-8")
        generated = build_english_entrypoint(source)
        self.assertEqual(generated, self.english_html)
        self.assertEqual(
            build_english_entrypoint(source),
            generated,
        )

    def test_committed_pair_is_deterministic_and_idempotent(self):
        french, english_document = build_documents(
            self.root_html,
            self.candidate_signals,
            self.recent_changes,
        )
        self.assertEqual(french, self.root_html)
        self.assertEqual(english_document, self.english_html)
        repeated = build_documents(
            french,
            self.candidate_signals,
            self.recent_changes,
        )
        self.assertEqual(repeated, (french, english_document))
        for document in repeated:
            self.assertEqual(document.count(WHAT_CHANGED_START), 1)
            self.assertEqual(document.count(WHAT_CHANGED_END), 1)
            self.assertEqual(document.count(RACE_START), 1)
            self.assertEqual(document.count(RACE_END), 1)

    def test_model_uses_only_approved_authoritative_artifacts(self):
        script = (ROOT / "build_search_entrypoints.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('ROOT / "candidate_signals.json"', script)
        self.assertIn('ROOT / "recent_changes.json"', script)
        for forbidden in (
            'ROOT / "polls.json"',
            'ROOT / "news_wire.json"',
            'ROOT / "claims_under_scrutiny.json"',
        ):
            self.assertNotIn(forbidden, script)

        model = construct_semantic_model(
            self.candidate_signals,
            self.recent_changes,
        )
        board = self.candidate_signals["featured_poll_board"]
        self.assertEqual(model["race"]["selected_event_id"], board["selected_event_id"])
        self.assertEqual(model["race"]["scenario_key"], board["scenario_key"])
        self.assertEqual(model["race"]["source_urls"], board["source_urls"])
        self.assertEqual(model["race"]["candidates"], board["candidates"])
        self.assertEqual(
            model["changes"]["items"],
            self.recent_changes["items"][:MAX_RECENT_CHANGES],
        )

    def test_candidate_and_ledger_order_are_preserved_without_extra_selection(self):
        changes_region = self.owned_region(
            self.root_html,
            WHAT_CHANGED_START,
            WHAT_CHANGED_END,
        )
        race_region = self.owned_region(
            self.root_html,
            RACE_START,
            RACE_END,
        )
        rendered_change_ids = re.findall(
            r'data-fr27-change-id="([^"]+)"', changes_region
        )
        rendered_candidate_ids = re.findall(
            r'data-fr27-candidate-id="([^"]+)"', race_region
        )
        self.assertEqual(
            rendered_change_ids,
            [
                item["id"]
                for item in self.recent_changes["items"][:MAX_RECENT_CHANGES]
            ],
        )
        self.assertLessEqual(len(rendered_change_ids), 3)
        self.assertEqual(
            rendered_candidate_ids,
            [
                candidate["candidate_id"]
                for candidate in self.candidate_signals[
                    "featured_poll_board"
                ]["candidates"]
            ],
        )

    def test_french_and_english_labels_are_localized_but_evidence_is_unchanged(self):
        french_changes = self.owned_region(
            self.root_html, WHAT_CHANGED_START, WHAT_CHANGED_END
        )
        english_changes = self.owned_region(
            self.english_html, WHAT_CHANGED_START, WHAT_CHANGED_END
        )
        french_race = self.owned_region(
            self.root_html, RACE_START, RACE_END
        )
        english_race = self.owned_region(
            self.english_html, RACE_START, RACE_END
        )
        self.assertIn("CE QUI A CHANGÉ", french_changes)
        self.assertIn("14 DERNIERS JOURS", french_changes)
        self.assertIn("RAPPORT DE FORCE", french_race)
        self.assertIn("Aucune moyenne", self.root_html)
        self.assertNotIn('class="race-interpretation"', french_race)
        self.assertIn("WHAT CHANGED", english_changes)
        self.assertIn("LAST 14 DAYS", english_changes)
        self.assertIn("RACE AT A GLANCE", english_race)
        self.assertIn("No averages", self.english_html)
        self.assertNotIn('class="race-interpretation"', english_race)

        board = self.candidate_signals["featured_poll_board"]
        for document_region in (french_race, english_race):
            self.assertIn(html.escape(board["pollster"]), document_region)
            for candidate in board["candidates"]:
                self.assertIn(
                    html.escape(candidate["candidate_name"]), document_region
                )
                score = format(candidate["reported_score"], "g")
                self.assertIn(
                    f'<data class="score" value="{score}">{score}%</data>',
                    document_region,
                )
            for url in board["source_urls"]:
                self.assertIn(html.escape(url, quote=True), document_region)

        for item in self.recent_changes["items"][:MAX_RECENT_CHANGES]:
            for document_region in (french_changes, english_changes):
                self.assertIn(html.escape(item["headline"]), document_region)
                self.assertIn(
                    html.escape(item["primary_source"]["name"]),
                    document_region,
                )
                self.assertIn(
                    html.escape(item["primary_source"]["url"], quote=True),
                    document_region,
                )

    def test_semantic_snapshot_is_visible_body_content_before_runtime(self):
        body = self.root_html[self.root_html.index("<body>") :]
        runtime = body.index("function renderWhatChanged()")
        for marker in (WHAT_CHANGED_START, RACE_START):
            self.assertLess(body.index(marker), runtime)
        changes = self.owned_region(
            body, WHAT_CHANGED_START, WHAT_CHANGED_END
        )
        race = self.owned_region(body, RACE_START, RACE_END)
        for region in (changes, race):
            self.assertNotIn("visually-hidden", region)
            self.assertNotIn("display:none", region.replace(" ", ""))
            self.assertNotIn("<noscript", region)
            self.assertIn("<ol", region)
            self.assertIn("<a", region)
        self.assertIn("<time", changes)
        self.assertIn("<time", race)
        self.assertIn("<data", race)

    def test_valid_empty_recent_changes_renders_localized_visible_state(self):
        empty = copy.deepcopy(self.recent_changes)
        empty["items"] = []
        empty["counts"] = {
            key: 0 for key in self.recent_changes["counts"]
        }
        empty["newest_trusted_change_at"] = None
        empty["oldest_trusted_change_at"] = None
        model = construct_semantic_model(self.candidate_signals, empty)
        french = render_semantic_regions(self.root_html, model, "fr")
        english_document = render_semantic_regions(
            self.root_html, model, "en"
        )
        french_region = self.owned_region(
            french, WHAT_CHANGED_START, WHAT_CHANGED_END
        )
        english_region = self.owned_region(
            english_document, WHAT_CHANGED_START, WHAT_CHANGED_END
        )
        self.assertIn(
            "Aucun changement qualifié dans les 14 derniers jours.",
            french_region,
        )
        self.assertIn(
            "No qualifying change in the last 14 days.", english_region
        )
        self.assertNotIn("data-fr27-change-id", french_region)

    def test_invalid_input_failure_leaves_both_documents_unchanged(self):
        with temporary_workspace() as temporary:
            source = temporary / "index.html"
            english_output = temporary / "en" / "index.html"
            candidate_signals = temporary / "candidate_signals.json"
            recent_changes = temporary / "recent_changes.json"
            english_output.parent.mkdir()
            source.write_bytes(INDEX.read_bytes())
            english_output.write_bytes(ENGLISH_INDEX.read_bytes())
            candidate_signals.write_bytes(CANDIDATE_SIGNALS.read_bytes())
            recent_changes.write_text("{}\n", encoding="utf-8")
            before = (source.read_bytes(), english_output.read_bytes())

            with self.assertRaises(SearchEntrypointError):
                generate_entrypoints(
                    source_path=source,
                    english_output_path=english_output,
                    candidate_signals_path=candidate_signals,
                    recent_changes_path=recent_changes,
                )

            self.assertEqual(
                (source.read_bytes(), english_output.read_bytes()), before
            )

    def test_pair_write_rolls_back_if_second_replace_fails(self):
        with temporary_workspace() as temporary:
            source = temporary / "index.html"
            english_output = temporary / "en" / "index.html"
            english_output.parent.mkdir()
            source.write_text(
                self.root_html.replace("CE QUI A CHANGÉ", "ÉTAT PÉRIMÉ", 1),
                encoding="utf-8",
            )
            english_output.write_text("stale English", encoding="utf-8")
            before = (source.read_bytes(), english_output.read_bytes())
            real_replace = os.replace
            calls = 0

            def fail_second_replace(from_path, to_path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated English replacement failure")
                return real_replace(from_path, to_path)

            with mock.patch(
                "build_search_entrypoints.os.replace",
                side_effect=fail_second_replace,
            ):
                with self.assertRaises(OSError):
                    generate_entrypoints(
                        source_path=source,
                        english_output_path=english_output,
                        candidate_signals_path=CANDIDATE_SIGNALS,
                        recent_changes_path=RECENT_CHANGES,
                    )

            self.assertEqual(
                (source.read_bytes(), english_output.read_bytes()), before
            )

    def test_check_mode_detects_stale_root_or_english_output(self):
        with temporary_workspace() as temporary:
            source = temporary / "index.html"
            english_output = temporary / "en" / "index.html"
            english_output.parent.mkdir()
            source.write_bytes(INDEX.read_bytes())
            english_output.write_bytes(ENGLISH_INDEX.read_bytes())
            paths = {
                "source_path": source,
                "english_output_path": english_output,
                "candidate_signals_path": CANDIDATE_SIGNALS,
                "recent_changes_path": RECENT_CHANGES,
                "check": True,
            }
            self.assertEqual(generate_entrypoints(**paths), (False, False))

            source.write_text(
                self.root_html.replace("CE QUI A CHANGÉ", "PÉRIMÉ", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SearchEntrypointError, "index.html"):
                generate_entrypoints(**paths)

            source.write_bytes(INDEX.read_bytes())
            english_output.write_text("stale English", encoding="utf-8")
            with self.assertRaisesRegex(
                SearchEntrypointError, r"en[/\\]index.html"
            ):
                generate_entrypoints(**paths)

    def test_runtime_preserves_snapshot_until_valid_data_replaces_it(self):
        runtime = self.root_html
        loading_guard = (
            '(ledger.loading || ledger.unavailable) &&\n'
            '        container.dataset.fr27SemanticSnapshot === "true"'
        )
        self.assertIn(loading_guard, runtime)
        self.assertIn(
            'container.removeAttribute("data-fr27-semantic-snapshot")',
            runtime,
        )
        self.assertLess(
            runtime.index(loading_guard),
            runtime.index("container.replaceChildren()", runtime.index(loading_guard)),
        )
        self.assertIn("const deliveredRaceSnapshot = (() => {", runtime)
        self.assertIn(
            'snapshotPanel?.dataset.fr27SemanticSnapshot === "true"',
            runtime,
        )
        self.assertIn(
            "deliveredRaceSnapshot.panel.cloneNode(true)", runtime
        )
        loaded_marker = runtime.index(
            'markDataset(\n          "polls",\n          "loaded"'
        )
        success_handoff = runtime.index(
            'removeAttribute(\n          "data-fr27-semantic-snapshot"',
            loaded_marker,
        )
        catch = runtime.index(".catch(error => {", success_handoff)
        self.assertLess(loaded_marker, success_handoff)
        self.assertLess(success_handoff, catch)

    def test_four_authoritative_writers_regenerate_and_stage_exact_html_pair(self):
        workflows = {
            name: (ROOT / ".github" / "workflows" / filename).read_text(
                encoding="utf-8"
            )
            for name, filename in {
                "polls": "update-polls.yml",
                "news": "update-news-wire.yml",
                "claims": "update-claims-under-scrutiny.yml",
                "candidate_universe": "update-candidate-universe.yml",
            }.items()
        }
        for name, workflow in workflows.items():
            with self.subTest(workflow=name):
                first_generator = workflow.index(
                    "python -B build_search_entrypoints.py"
                )
                first_manifest = workflow.index(
                    "build_publication_manifest"
                )
                self.assertLess(first_generator, first_manifest)
                commit = workflow.index("git commit")
                stage = workflow[workflow.rfind("git add --", 0, commit) : commit]
                self.assertIn("index.html", stage)
                self.assertIn("en/index.html", stage)
                self.assertNotIn("git add -A", workflow)
                self.assertNotIn("git add --all", workflow)

        for name in ("news", "claims", "candidate_universe"):
            with self.subTest(post_rebase=name):
                workflow = workflows[name]
                rebase = workflow.index("git rebase ")
                generator = workflow.index(
                    "build_search_entrypoints", rebase
                )
                if name == "candidate_universe":
                    manifest = workflow.index("build_manifest", generator)
                else:
                    manifest = workflow.index(
                        "build_publication_manifest.py", generator
                    )
                self.assertLess(rebase, generator)
                self.assertLess(generator, manifest)
                amendment = workflow[
                    generator : workflow.index(
                        "git commit --amend --no-edit", generator
                    )
                ]
                self.assertIn("index.html", amendment)
                self.assertIn("en/index.html", amendment)

        candidate_attention = (
            ROOT / ".github" / "workflows" / "update-candidate-attention.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("build_search_entrypoints", candidate_attention)

    def test_writer_transaction_order_and_exact_initial_stage_sets(self):
        workflows = {
            name: (ROOT / ".github" / "workflows" / filename).read_text(
                encoding="utf-8"
            )
            for name, filename in {
                "polls": "update-polls.yml",
                "news": "update-news-wire.yml",
                "claims": "update-claims-under-scrutiny.yml",
                "candidate_universe": "update-candidate-universe.yml",
            }.items()
        }
        derived_markers = {
            "polls": (
                "python generate_recent_changes.py",
                "python -B build_candidate_signals.py",
            ),
            "news": (
                "python generate_recent_changes.py",
                "python -B build_candidate_signals.py",
            ),
            "claims": (
                "python generate_recent_changes.py",
                "python -B build_candidate_signals.py",
            ),
            "candidate_universe": (
                "Rebuild Candidate Agenda History on registry change",
                "Rebuild Candidate Signals on registry change",
            ),
        }
        expected_stage_sets = {
            "polls": {
                "polls.json",
                "second_round_polls.json",
                "closest_tested_runoff.json",
                "commission_notice_registry.json",
                "recent_changes.json",
                "candidate_signals.json",
                "index.html",
                "en/index.html",
                "publication_manifest.json",
            },
            "news": {
                "news_inventory.json",
                "news_wire.json",
                "recent_changes.json",
                "source_health.json",
                "candidate_signals.json",
                "candidate_agenda_history.json",
                "candidate_visibility_history.json",
                "index.html",
                "en/index.html",
                "publication_manifest.json",
                "source_icons.json",
                "assets/source-icons",
            },
            "claims": {
                "claims_under_scrutiny.json",
                "recent_changes.json",
                "candidate_signals.json",
                "index.html",
                "en/index.html",
                "publication_manifest.json",
            },
            "candidate_universe": {
                "candidate_candidacy_status.json",
                "campaign_events.json",
                "candidate_signals.json",
                "candidate_agenda_history.json",
                "candidate_visibility_history.json",
                "index.html",
                "en/index.html",
                "publication_manifest.json",
            },
        }

        for name, workflow in workflows.items():
            with self.subTest(workflow=name):
                generator = workflow.index(
                    "python -B build_search_entrypoints.py"
                )
                manifest_step = workflow.index(
                    "\n      - name: Rebuild", generator
                )
                for marker in derived_markers[name]:
                    self.assertLess(workflow.index(marker), generator)
                self.assertLess(generator, manifest_step)

                stage_start = workflow.index("git add --")
                stage_end = workflow.index("git commit", stage_start)
                stage = workflow[stage_start:stage_end]
                staged_paths = set(
                    re.findall(
                        r"[A-Za-z0-9_./-]+(?:\.json|\.html)", stage
                    )
                )
                if "assets/source-icons" in stage:
                    staged_paths.add("assets/source-icons")
                self.assertEqual(staged_paths, expected_stage_sets[name])

    def test_sitemap_contains_only_canonical_language_urls(self):
        tree = ET.parse(SITEMAP)
        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [
            node.text
            for node in tree.findall("sm:url/sm:loc", namespace)
        ]
        self.assertEqual(urls, [ROOT_URL, ENGLISH_URL])
        for url in urls:
            self.assertNotIn("www.", url)
            self.assertNotIn("?lang=", url)

    def test_robots_is_permissive_and_advertises_sitemap(self):
        text = ROBOTS.read_text(encoding="utf-8")
        self.assertEqual(
            text,
            "User-agent: *\n"
            "Allow: /\n"
            "\n"
            "Sitemap: https://france2027.app/sitemap.xml\n",
        )

    def test_og_cover_workflow_regenerates_and_stages_english_entrypoint(self):
        workflow = (
            ROOT / ".github" / "workflows" / "refresh-og-cover.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "python .\\build_search_entrypoints.py",
            workflow,
        )
        self.assertIn(
            "python -m unittest test_search_foundation.py",
            workflow,
        )
        self.assertIn(
            '"en/index.html",',
            workflow,
        )
        self.assertIn(
            "            en/index.html `",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
