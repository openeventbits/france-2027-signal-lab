from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

import build_poll_explorer as explorer
from build_candidate_signals import build_poll_packages, validated_first_round_events


ROOT = Path(__file__).resolve().parent
FORBIDDEN_KEY_PARTS = {
    "average",
    "forecast",
    "probability",
    "momentum",
    "trend_score",
    "modeled_score",
    "modelled_score",
    "prediction",
}


def package_key(event):
    return (
        event["pollster"],
        event["fieldwork_start"],
        event["fieldwork_end"],
        event.get("sample_size"),
    )


def recursive_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from recursive_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from recursive_keys(child)


class PollExplorerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.polls = explorer.load_polls(ROOT / "polls.json")
        cls.validated = validated_first_round_events(cls.polls)
        cls.packages = build_poll_packages(cls.polls)
        cls.payload = explorer.build_poll_explorer(copy.deepcopy(cls.polls))

    def test_builder_accepts_current_polls(self):
        self.assertEqual(self.payload["schema_version"], "1.0")
        self.assertEqual(
            self.payload["metrics"]["scenario_count"],
            len(self.validated),
        )

    def test_builder_is_deterministic(self):
        first = explorer.serialize_poll_explorer(
            explorer.build_poll_explorer(copy.deepcopy(self.polls))
        )
        second = explorer.serialize_poll_explorer(
            explorer.build_poll_explorer(copy.deepcopy(self.polls))
        )
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))

    def test_wave_ids_are_unique_and_readable(self):
        wave_ids = [wave["wave_id"] for wave in self.payload["waves"]]
        self.assertEqual(len(wave_ids), len(set(wave_ids)))
        self.assertTrue(
            all(re.fullmatch(r"wave-[0-9a-f]{16}", wave_id) for wave_id in wave_ids)
        )

    def test_wave_page_routes_are_unique_and_stable(self):
        slugs = [wave["page_slug"] for wave in self.payload["waves"]]
        paths_fr = [wave["page_path_fr"] for wave in self.payload["waves"]]
        paths_en = [wave["page_path_en"] for wave in self.payload["waves"]]

        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertEqual(len(paths_fr), len(set(paths_fr)))
        self.assertEqual(len(paths_en), len(set(paths_en)))

        for wave in self.payload["waves"]:
            with self.subTest(wave_id=wave["wave_id"]):
                token = wave["wave_id"].removeprefix("wave-")

                expected_slug = explorer.poll_wave_page_slug(
                    fieldwork_end=wave["fieldwork_end"],
                    pollster=wave["pollster"],
                    wave_id=wave["wave_id"],
                )

                self.assertEqual(wave["page_slug"], expected_slug)
                self.assertTrue(wave["page_slug"].endswith(f"-{token}"))
                self.assertRegex(
                    wave["page_slug"],
                    r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{16}$",
                )
                self.assertEqual(
                    wave["page_path_fr"],
                    f"/sondages/{wave['page_slug']}/",
                )
                self.assertEqual(
                    wave["page_path_en"],
                    f"/en/sondages/{wave['page_slug']}/",
                )


    def test_wave_route_slug_normalizes_pollster_names(self):
        slug = explorer.poll_wave_page_slug(
            fieldwork_end="2026-09-10",
            pollster="Ifop/Hexagone",
            wave_id="wave-0123456789abcdef",
        )
        self.assertEqual(
            slug,
            "2026-09-10-ifop-hexagone-0123456789abcdef",
        )

        accented = explorer.poll_wave_page_slug(
            fieldwork_end="2026-09-10",
            pollster="Élan Études",
            wave_id="wave-fedcba9876543210",
        )
        self.assertEqual(
            accented,
            "2026-09-10-elan-etudes-fedcba9876543210",
        )


    def test_wave_route_identity_does_not_depend_on_collision_state(self):
        first = explorer.poll_wave_page_slug(
            fieldwork_end="2025-10-01",
            pollster="Cluster17",
            wave_id="wave-443d8f942e9b4eca",
        )
        second = explorer.poll_wave_page_slug(
            fieldwork_end="2025-10-01",
            pollster="Cluster17",
            wave_id="wave-aaaaaaaaaaaaaaaa",
        )

        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("2025-10-01-cluster17-"))
        self.assertTrue(second.startswith("2025-10-01-cluster17-"))


    def test_polling_lab_internal_wave_graph_contract(self):
        script = (
            ROOT / "assets" / "polling-lab.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'const key = PAGE_LANG === "en" '
            '? "page_path_en" : "page_path_fr";',
            script,
        )

        fr_start = script.index(
            '    fr: Object.freeze({'
        )
        en_start = script.index(
            '    en: Object.freeze({'
        )
        ui_end = script.index(
            "\n    })\n  });",
            en_start,
        )

        fr_block = script[fr_start:en_start]
        en_block = script[en_start:ui_end]

        self.assertEqual(
            fr_block.count('openPoll: "OUVRIR →"'),
            1,
        )
        self.assertEqual(
            fr_block.count('pollPage: "SONDAGE"'),
            1,
        )
        self.assertEqual(
            fr_block.count(
                'pageUnavailable: "PAGE INDISPONIBLE"'
            ),
            1,
        )

        self.assertNotIn(
            'openPoll: "OPEN →"',
            fr_block,
        )

        self.assertEqual(
            en_block.count('openPoll: "OPEN →"'),
            1,
        )
        self.assertEqual(
            en_block.count('pollPage: "POLL"'),
            1,
        )
        self.assertEqual(
            en_block.count(
                'pageUnavailable: "PAGE UNAVAILABLE"'
            ),
            1,
        )

        self.assertNotIn(
            'openPoll: "OUVRIR →"',
            en_block,
        )


    def test_polling_lab_no_longer_links_directly_to_poll_sources(self):
        script = (
            ROOT / "assets" / "polling-lab.js"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "scenario.source_url",
            script,
        )

        self.assertNotIn(
            "(wave.source_urls || [])",
            script,
        )

        self.assertNotIn(
            "safeHttpUrl(",
            script,
        )

        self.assertNotIn(
            'target = "_blank"',
            script[
                script.index("function openCellForWave"):
                script.index("function renderLatestWaves")
            ],
        )

    def test_inspector_links_to_exact_generated_scenario_anchor(self):
        script = (
            ROOT / "assets" / "polling-lab.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "function scenarioPageHref(wave, scenario)",
            script,
        )

        self.assertIn(
            "item?.event_id === scenario?.event_id",
            script,
        )

        self.assertIn(
            "`${base}#scenario-${index + 1}`",
            script,
        )

        self.assertIn(
            '"polling-inspector-wave-link"',
            script,
        )

    def test_wave_directories_use_descriptive_internal_links(self):
        script = (
            ROOT / "assets" / "polling-lab.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "function createWavePageLink(",
            script,
        )

        self.assertGreaterEqual(
            script.count(
                "createWavePageLink("
            ),
            6,
        )

        self.assertIn(
            "function openCellForWave(wave)",
            script,
        )

        self.assertIn(
            'uiText("pollPage")',
            script,
        )

        self.assertNotIn(
            "sourceCellForWave",
            script,
        )

    def test_every_wave_internal_destination_is_language_safe(self):
        for wave in self.payload["waves"]:
            with self.subTest(
                wave_id=wave["wave_id"]
            ):
                self.assertRegex(
                    wave["page_path_fr"],
                    r"^/sondages/"
                    r"\d{4}-\d{2}-\d{2}-"
                    r"[a-z0-9-]+-[0-9a-f]{16}/$",
                )

                self.assertRegex(
                    wave["page_path_en"],
                    r"^/en/sondages/"
                    r"\d{4}-\d{2}-\d{2}-"
                    r"[a-z0-9-]+-[0-9a-f]{16}/$",
                )


    def test_scenario_event_ids_are_unique_and_belong_to_one_wave(self):
        event_ids = [
            scenario["event_id"]
            for wave in self.payload["waves"]
            for scenario in wave["scenarios"]
        ]
        self.assertEqual(len(event_ids), len(set(event_ids)))
        self.assertEqual(len(event_ids), len(self.validated))

    def test_wave_grouping_count_matches_race_at_a_glance_packages(self):
        self.assertEqual(len(self.payload["waves"]), len(self.packages))
        expected = {
            (
                package["pollster"],
                package["fieldwork_start"],
                package["fieldwork_end"],
                package["sample_size"],
            ): {event["event_id"] for event in package["events"]}
            for package in self.packages
        }
        actual = {
            (
                wave["pollster"],
                wave["fieldwork_start"],
                wave["fieldwork_end"],
                wave["sample_size"],
            ): {scenario["event_id"] for scenario in wave["scenarios"]}
            for wave in self.payload["waves"]
        }
        self.assertEqual(actual, expected)

    def test_total_scenario_count_equals_valid_first_round_events(self):
        self.assertEqual(
            sum(wave["scenario_count"] for wave in self.payload["waves"]),
            len(self.validated),
        )

    def test_selected_event_id_belongs_to_each_wave(self):
        for wave in self.payload["waves"]:
            with self.subTest(wave_id=wave["wave_id"]):
                self.assertIn(
                    wave["selected_event_id"],
                    {scenario["event_id"] for scenario in wave["scenarios"]},
                )

    def test_scenario_keys_scores_and_source_urls_are_passed_through(self):
        source = {event["event_id"]: event for _index, event in self.validated}
        for wave in self.payload["waves"]:
            self.assertEqual(
                set(wave["source_urls"]),
                {source[event_id]["source_url"] for event_id in {
                    scenario["event_id"] for scenario in wave["scenarios"]
                }},
            )
            for scenario in wave["scenarios"]:
                with self.subTest(event_id=scenario["event_id"]):
                    event = source[scenario["event_id"]]
                    self.assertEqual(scenario["scenario_key"], event["scenario_key"])
                    self.assertEqual(scenario["source_url"], event["source_url"])
                    self.assertEqual(
                        [
                            (candidate["published_candidate_name"], candidate["score"])
                            for candidate in scenario["candidates"]
                        ],
                        [
                            (candidate["name"], candidate["score"])
                            for candidate in event["candidates"]
                        ],
                    )
                    for projected, source_candidate in zip(
                        scenario["candidates"], event["candidates"], strict=True
                    ):
                        expected_name = explorer.EXPLICIT_CANDIDATE_ALIASES.get(
                            source_candidate["name"], source_candidate["name"]
                        )
                        self.assertEqual(projected["candidate_name"], expected_name)

    def test_candidate_ids_are_deterministic_and_aliases_are_explicit(self):
        first = {
            candidate["candidate_name"]: candidate["candidate_id"]
            for candidate in self.payload["candidates"]
        }
        second_payload = explorer.build_poll_explorer(copy.deepcopy(self.polls))
        second = {
            candidate["candidate_name"]: candidate["candidate_id"]
            for candidate in second_payload["candidates"]
        }
        self.assertEqual(first, second)
        self.assertEqual(len(first.values()), len(set(first.values())))

        source_names = {
            candidate["name"]
            for _index, event in self.validated
            for candidate in event["candidates"]
        }
        directory_labels = {
            label
            for candidate in self.payload["candidates"]
            for label in candidate["source_labels"]
        }
        expected_person_labels = source_names - explorer.BALLOT_LABEL_IDENTITIES
        self.assertEqual(directory_labels, expected_person_labels)

        for published_name, canonical_name in explorer.EXPLICIT_CANDIDATE_ALIASES.items():
            if published_name not in source_names:
                continue
            self.assertIn(canonical_name, first)
            self.assertNotIn(published_name, first)

        self.assertTrue(
            explorer.BALLOT_LABEL_IDENTITIES.isdisjoint(directory_labels)
        )

    def test_observed_ranges_require_only_actual_person_observations(self):
        source = {event["event_id"]: event for _index, event in self.validated}
        candidate_ids = {
            candidate["candidate_name"]: candidate["candidate_id"]
            for candidate in self.payload["candidates"]
        }
        for wave in self.payload["waves"]:
            observed: dict[str, list[int | float]] = {}
            expected: dict[str, list[int | float]] = {}
            for scenario in wave["scenarios"]:
                for candidate in scenario["candidates"]:
                    if candidate["identity_type"] != "person":
                        continue
                    observed.setdefault(candidate["candidate_id"], []).append(
                        candidate["score"]
                    )
                for candidate in source[scenario["event_id"]]["candidates"]:
                    if candidate["name"] in explorer.BALLOT_LABEL_IDENTITIES:
                        continue
                    canonical_name = explorer.EXPLICIT_CANDIDATE_ALIASES.get(
                        candidate["name"], candidate["name"]
                    )
                    expected.setdefault(candidate_ids[canonical_name], []).append(
                        candidate["score"]
                    )

            self.assertEqual(observed, expected)
            for candidate_id, scores in observed.items():
                actual_range = (min(scores), max(scores), max(scores) - min(scores))
                source_scores = expected[candidate_id]
                source_range = (
                    min(source_scores),
                    max(source_scores),
                    max(source_scores) - min(source_scores),
                )
                self.assertEqual(actual_range, source_range)
                if len(scores) == 1:
                    self.assertEqual(actual_range[0], actual_range[1])

    def test_scenario_identity_types_preserve_generic_ballot_labels(self):
        for wave in self.payload["waves"]:
            for scenario in wave["scenarios"]:
                for candidate in scenario["candidates"]:
                    published_name = candidate["published_candidate_name"]
                    expected_type = (
                        "ballot_label"
                        if published_name in explorer.BALLOT_LABEL_IDENTITIES
                        else "person"
                    )
                    self.assertEqual(candidate["identity_type"], expected_type)
                    if expected_type == "ballot_label":
                        self.assertEqual(candidate["candidate_name"], published_name)

    def test_no_interpretive_or_modeled_fields_are_introduced(self):
        keys = {key.casefold() for key in recursive_keys(self.payload)}
        for forbidden in FORBIDDEN_KEY_PARTS:
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in key for key in keys),
                    f"forbidden field part present: {forbidden}",
                )


    def test_picker_uses_active_monitoring_candidate_universe(self):
        signals = json.loads((ROOT / "candidate_signals.json").read_text(encoding="utf-8"))
        active = signals["active_monitoring_field"]
        active_ids = [*active["main"], *active["secondary"]]
        self.assertEqual(len(active_ids), len(set(active_ids)))
        self.assertEqual(active["counts"]["active"], len(active_ids))

        tested_ids = {candidate["candidate_id"] for candidate in self.payload["candidates"]}
        picker_ids = [candidate_id for candidate_id in active_ids if candidate_id in tested_ids]
        self.assertTrue(picker_ids)
        self.assertTrue(set(picker_ids).issubset(set(active_ids)))

        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertIn('const ROOT_PREFIX = PAGE_LANG === "en" ? "../.." : "..";', frontend)
        self.assertIn('const CANDIDATE_SIGNALS_URL = `${ROOT_PREFIX}/candidate_signals.json`;', frontend)
        self.assertIn("active_monitoring_field", frontend)

    def test_picker_sort_uses_latest_actual_poll_observations(self):
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertIn("candidateLatestPollMeta", frontend)
        self.assertIn("sortScore: maximum", frontend)
        self.assertIn("return rightScore - leftScore", frontend)
        self.assertNotIn("sortAverage", frontend)
        self.assertNotIn("sortMidpoint", frontend)
        self.assertIn("meta.minimum === meta.maximum", frontend)
        self.assertIn("formatScore(meta.minimum)}–${formatScore(meta.maximum)", frontend)


    def test_historical_chart_uses_only_published_observations(self):
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertIn("scoreObservationsForWave", frontend)
        self.assertIn("item.score", frontend)
        self.assertIn("Math.min(...scores)", frontend)
        self.assertIn("Math.max(...scores)", frontend)
        self.assertNotIn("interpolate", frontend.casefold())
        self.assertNotIn("smoothing", frontend.casefold())

    def test_comparable_chart_requires_exact_pollster_scenario_and_all_selected_candidates(self):
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertIn("sharedComparableSeriesKey", frontend)
        self.assertIn("wave.pollster", frontend)
        self.assertIn("scenario.scenario_key", frontend)
        self.assertIn("selectedCandidatesForScenario", frontend)
        self.assertIn("for (const candidateId of state.selectedCandidateIds)", frontend)
        self.assertIn("if (!candidate) return null", frontend)
        self.assertIn("item.wave.wave_id", frontend)
        self.assertIn(".size >= 2", frontend)

    def test_historical_observation_inspector_links_internal_evidence_page(self):
        frontend = (
            ROOT / "assets" / "polling-lab.js"
        ).read_text(encoding="utf-8")

        # Published source evidence remains in the canonical data.
        historical_sources = [
            scenario.get("source_url")
            for wave in self.payload["waves"]
            for scenario in wave["scenarios"]
            if scenario.get("source_url")
        ]

        self.assertTrue(historical_sources)

        # But the Polling Lab now routes readers through the
        # canonical internal poll-wave evidence page.
        self.assertNotIn(
            "scenario.source_url",
            frontend,
        )

        self.assertIn(
            "function scenarioPageHref(wave, scenario)",
            frontend,
        )

        self.assertIn(
            "item?.event_id === scenario?.event_id",
            frontend,
        )

        self.assertIn(
            "`${base}#scenario-${index + 1}`",
            frontend,
        )

        self.assertIn(
            'openPage.textContent = uiText("openPoll")',
            frontend,
        )


    def test_comparable_dumbbell_supports_series_focus_and_persistent_selection(self):
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertIn("updateComparableSeriesEmphasis", frontend)
        self.assertIn("selectedComparableSeriesKey", frontend)
        self.assertIn("selectedObservationEventId", frontend)
        self.assertIn("selectedObservationCandidateId", frontend)
        self.assertIn("polling-comparable-series-group", frontend)
        self.assertIn("polling-comparable-stem", frontend)
        self.assertIn("polling-comparable-observation", frontend)
        self.assertIn("mouseenter", frontend)
        self.assertIn("mouseleave", frontend)
        self.assertIn("previewSeries", frontend)
        self.assertIn("selectSeries", frontend)

    def test_comparable_inspector_explains_exact_repeated_ballot(self):
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertIn("BULLETIN EXACT RÉPÉTÉ", frontend)
        self.assertIn("Même institut + même scénario", frontend)
        self.assertIn("series.occurrences", frontend)
        self.assertIn("distinctWaveCount", frontend)

    def test_comparable_mode_preserves_real_calendar_time_and_shared_wave_comparison(self):
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertIn("renderComparableDumbbellTimeline", frontend)
        self.assertIn("xFor(occurrence.wave.fieldwork_end)", frontend)
        self.assertIn("domainStart = periodStartDate().getTime()", frontend)
        self.assertIn("domainEnd = new Date(`${state.data.data_as_of}T00:00:00Z`).getTime()", frontend)
        self.assertIn("Math.min(...scores)", frontend)
        self.assertIn("Math.max(...scores)", frontend)
        self.assertIn("Chaque tige relie les candidats sélectionnés testés dans la même vague", frontend)
        self.assertIn("COMPARAISON À BULLETIN IDENTIQUE", frontend)
        self.assertIn("PARTAGÉE", frontend)
        self.assertIn("polling-comparable-active-label", frontend)
        self.assertNotIn("gridColumn = String(index + 1)", frontend)
        self.assertNotIn("renderComparableLedger", frontend)

    def test_comparable_paths_are_hidden_until_exact_series_is_selected(self):
        styles = (ROOT / "assets" / "polling-lab.css").read_text(encoding="utf-8")
        self.assertIn(".polling-comparable-series-path", styles)
        self.assertIn("opacity: 0;", styles)
        self.assertIn(".polling-comparable-series-group.is-active .polling-comparable-series-path", styles)
        self.assertIn(".polling-comparable-series-group.is-muted", styles)
        self.assertIn(".polling-comparable-observation.is-selected-observation", styles)
        self.assertIn(".polling-comparable-stem", styles)

    def test_browse_section_is_functional_not_placeholder(self):
        html = (ROOT / "sondages" / "index.html").read_text(encoding="utf-8")
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertNotIn("À VENIR", html)
        self.assertIn('id="polling-browse-tabs"', html)
        self.assertIn('id="polling-browse-panel"', html)
        self.assertIn('data-browse-mode="all"', html)
        self.assertIn('data-browse-mode="institutes"', html)
        self.assertIn('data-browse-mode="candidates"', html)
        self.assertIn("renderBrowseExplorer", frontend)
        self.assertIn("renderBrowseAll", frontend)
        self.assertIn("renderBrowseInstitutes", frontend)
        self.assertIn("renderBrowseCandidates", frontend)

    def test_browse_candidate_detail_uses_actual_observed_scores_only(self):
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertIn("candidateWaveScoreMeta", frontend)
        self.assertIn("Math.min(...scores)", frontend)
        self.assertIn("Math.max(...scores)", frontend)
        self.assertIn("scoreMeta.minimum === scoreMeta.maximum", frontend)
        self.assertNotIn("browseAverage", frontend)
        self.assertNotIn("browseForecast", frontend)

    def test_browse_indexes_reuse_current_directories_and_candidate_universe(self):
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        self.assertIn("state.data.institutes", frontend)
        self.assertIn("state.pickerCandidates", frontend)
        self.assertIn("candidateBrowseWaves", frontend)
        self.assertIn("data-browse-compare-candidate", frontend)
        self.assertIn("addCandidate(compare.dataset.browseCompareCandidate)", frontend)

    def test_metrics_and_period_are_source_derived(self):
        events = [event for _index, event in self.validated]
        metrics = self.payload["metrics"]
        self.assertEqual(metrics["period_start"], min(event["fieldwork_start"] for event in events))
        self.assertEqual(metrics["period_end"], max(event["fieldwork_end"] for event in events))
        self.assertEqual(self.payload["data_as_of"], metrics["period_end"])
        self.assertEqual(metrics["candidate_count"], len(self.payload["candidates"]))
        self.assertEqual(metrics["institute_count"], len(self.payload["institutes"]))


    def test_polling_hud_count_tracks_source_wave_metric(self):
        frontend = (
            ROOT / "assets" / "polling-lab.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'hudPollsValue: byId("fr27-hud-polls-value")',
            frontend,
        )
        self.assertIn(
            "nodes.hudPollsValue.textContent = "
            "formatInteger(metrics.wave_count);",
            frontend,
        )

        placeholder = (
            '<strong id="fr27-hud-polls-value">—</strong>'
        )

        for relative in (
            Path("sondages/index.html"),
            Path("en/sondages/index.html"),
        ):
            html = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(placeholder, html)


    def test_polling_lab_uses_shared_standalone_visual_contract(self):
        styles = (ROOT / "assets" / "polling-lab.css").read_text(encoding="utf-8")
        self.assertIn("/* === STANDALONE FR27 VISUAL CONTRACT ===", styles)
        self.assertIn("--fr27-type-panel-heading: 15.5px;", styles)
        self.assertIn("--fr27-type-body: 13px;", styles)
        self.assertIn("--fr27-type-meta: 13px;", styles)
        self.assertIn("--fr27-type-control: 13px;", styles)
        self.assertIn("--fr27-type-note: 12px;", styles)
        self.assertIn("--fr27-num-kpi: 20px;", styles)
        self.assertIn("width: 52px;", styles)
        self.assertIn("height: 52px;", styles)
        self.assertIn("font-size: var(--fr27-type-meta);", styles)
        self.assertIn("font-size: var(--fr27-type-control);", styles)



    def test_polling_lab_uses_exact_candidate_reference_header_and_footer(self):
        html = (ROOT / "sondages" / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="candidate-masthead"', html)
        self.assertIn('class="candidate-brand"', html)
        self.assertIn('class="candidate-language"', html)
        self.assertIn('class="candidate-countdown"', html)
        self.assertIn('id="candidate-app-hud"', html)
        self.assertIn('class="fr27-app-hud"', html)
        self.assertIn('id="fr27-hud-paris-time"', html)
        self.assertIn('id="fr27-hud-countdown-days"', html)
        self.assertIn('class="fr27-dashboard-cta"', html)
        self.assertIn('id="fr27-hud-email-toggle"', html)
        self.assertIn('id="fr27-hud-info-toggle"', html)
        self.assertNotIn('class="polling-masthead"', html)
        self.assertNotIn('class="polling-methodology"', html)

    def test_candidate_reference_shell_is_transplanted_as_polling_shell_contract(self):
        html = (ROOT / "sondages" / "index.html").read_text(encoding="utf-8")
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")
        shell_path = ROOT / "assets" / "polling-page-shell.css"
        self.assertTrue(shell_path.exists(), "polling-page-shell.css must be derived from the candidate reference shell")
        shell = shell_path.read_text(encoding="utf-8")
        self.assertIn('href="../assets/polling-page-shell.css"', html)
        self.assertIn('class="polling-page"', html)
        self.assertIn(".polling-page .candidate-masthead", shell)
        self.assertIn(".polling-page .candidate-brand-copy strong", shell)
        self.assertIn(".polling-page #candidate-app-hud.fr27-app-hud", shell)
        self.assertIn("FR27 APPLICATION HUD — CANDIDATE-PAGE TRANSPLANT", shell)
        self.assertIn("initApplicationHud", frontend)
        self.assertIn("Europe/Paris", frontend)
        self.assertIn('document.querySelector("[data-countdown] .candidate-countdown-value")', frontend)



    def test_french_inspector_normalizes_raw_scenario_vocabulary(self):
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")

        raw_hypotheses = [
            scenario.get("hypothesis", "")
            for wave in self.payload["waves"]
            for scenario in wave["scenarios"]
        ]

        for prefix in ("First round", "French rehearsal", "French source"):
            self.assertTrue(
                any(value.startswith(prefix) for value in raw_hypotheses),
                f"fixture must contain raw {prefix!r} hypotheses",
            )
            self.assertNotIn(prefix, frontend)

        raw_candidate_labels = [
            candidate.get("published_candidate_name", "")
            for wave in self.payload["waves"]
            for scenario in wave["scenarios"]
            for candidate in scenario["candidates"]
        ]

        self.assertTrue(
            any(label.startswith("Generic ") for label in raw_candidate_labels),
            "fixture must contain Generic source labels",
        )

        self.assertNotIn(
            "scenario.hypothesis || scenario.scenario_key",
            frontend,
        )
        self.assertIn("displayScenarioCandidate", frontend)
        self.assertIn('replace(/^Generic\\s+/i, "")', frontend)
        self.assertIn('firstRound: "PREMIER TOUR"', frontend)
        self.assertIn('`${uiText("firstRound")} — ${scenarioCandidates.join(", ")}`', frontend)

    def test_english_polling_lab_route_contract(self):
        fr_path = ROOT / "sondages" / "index.html"
        en_path = ROOT / "en" / "sondages" / "index.html"

        self.assertTrue(fr_path.exists())
        self.assertTrue(en_path.exists())

        fr = fr_path.read_text(encoding="utf-8")
        en = en_path.read_text(encoding="utf-8")
        frontend = (ROOT / "assets" / "polling-lab.js").read_text(encoding="utf-8")

        # Route language and shared implementation.
        self.assertIn('<html lang="fr">', fr)
        self.assertIn('<html lang="en">', en)
        self.assertIn('../../assets/polling-lab.css', en)
        self.assertIn('../../assets/polling-page-shell.css', en)
        self.assertIn('../../assets/polling-lab.js', en)
        self.assertIn(
            'document.documentElement.lang.toLowerCase().startsWith("en")',
            frontend,
        )

        # Canonical and language alternates.
        self.assertIn(
            'rel="canonical" href="https://france2027.app/sondages/"',
            fr,
        )
        self.assertIn(
            'rel="canonical" href="https://france2027.app/en/sondages/"',
            en,
        )

        for page in (fr, en):
            self.assertIn(
                'hreflang="fr" href="https://france2027.app/sondages/"',
                page,
            )
            self.assertIn(
                'hreflang="en" href="https://france2027.app/en/sondages/"',
                page,
            )
            self.assertIn(
                'hreflang="x-default" href="https://france2027.app/sondages/"',
                page,
            )

        # Bidirectional language control.
        self.assertIn(
            'href="/en/sondages/" lang="en" hreflang="en" aria-label="English">EN</a>',
            fr,
        )
        self.assertIn(
            'href="/sondages/" lang="fr" hreflang="fr" aria-label="Français">FR</a>',
            en,
        )
        self.assertIn(
            'aria-label="English" aria-current="page">EN</a>',
            en,
        )
        self.assertNotIn("Version anglaise à venir", fr)
        self.assertNotIn('aria-disabled="true" title="Version anglaise à venir"', fr)

        # Established English Polling Lab vocabulary.
        expected_english = (
            "Source-linked signals from the French presidential race.",
            "PUBLISHED OBSERVATIONS",
            "COMPARABLE BALLOTS",
            "EVIDENCE INSPECTOR",
            "SAME POLL · DIFFERENT BALLOTS",
            "VARIATION ACROSS PUBLISHED SCENARIOS",
            "LATEST POLL WAVES",
            "EXPLORE POLLS",
            "NO POLLING AVERAGES",
            "NO FORECAST",
            "NO VOTING ADVICE",
        )
        for phrase in expected_english:
            self.assertIn(phrase, en)

        # Known French static leaks must not return on the English route.
        forbidden_english_route_phrases = (
            ">jours</span>",
            "Couverture des données",
            "OBSERVATION PUBLIÉE",
            "La sélection d’une observation affichera",
            "Chargement des vagues",
            "L’étendue correspond uniquement",
            'aria-label="Explorer les sondages"',
        )
        for phrase in forbidden_english_route_phrases:
            self.assertNotIn(phrase, en)


if __name__ == "__main__":
    unittest.main()
