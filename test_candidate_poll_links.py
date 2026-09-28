from __future__ import annotations

from collections import Counter
from copy import deepcopy
from html.parser import HTMLParser
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_candidate_reference as reference


ROOT = Path(__file__).resolve().parent


class CandidatePollHTMLAuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.poll_panel_depth = 0
        self.directory_count = 0
        self.directories_outside_poll_panel = 0
        self.open_directory_count = 0
        self.hrefs: list[str | None] = []
        self.labels: list[str] = []
        self.ids: list[str] = []
        self._link_text: list[str] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        is_poll_panel = tag == "article" and "candidate-poll-history-panel" in classes
        self.stack.append((tag, is_poll_panel))
        if is_poll_panel:
            self.poll_panel_depth += 1

        element_id = attributes.get("id")
        if element_id:
            self.ids.append(element_id)

        if tag == "details" and "candidate-poll-history-directory" in classes:
            self.directory_count += 1
            if not self.poll_panel_depth:
                self.directories_outside_poll_panel += 1
            if "open" in attributes:
                self.open_directory_count += 1

        if tag == "a" and "candidate-poll-history-wave-link" in classes:
            self.hrefs.append(attributes.get("href"))
            self._link_text = []

    def handle_data(self, data: str) -> None:
        if self._link_text is not None:
            self._link_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._link_text is not None:
            self.labels.append(" ".join("".join(self._link_text).split()))
            self._link_text = None

        while self.stack:
            open_tag, is_poll_panel = self.stack.pop()
            if is_poll_panel:
                self.poll_panel_depth -= 1
            if open_tag == tag:
                break


class CandidatePollLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = reference.load_sources(ROOT)
        reference.validate_sources(cls.sources, ROOT)
        cls.hud = reference.derive_hud_metrics(cls.sources)
        cls.wave_index = reference.load_poll_wave_link_index(ROOT)

        registry = json.loads(
            (ROOT / "route_registry.json").read_text(encoding="utf-8")
        )
        cls.routes_by_path = {route["path"]: route for route in registry["routes"]}
        detail_routes = [
            route
            for route in registry["routes"]
            if route.get("family") == "candidates"
            and route.get("kind") == "candidate-detail"
        ]
        routes_by_candidate: dict[str, list[dict]] = {}
        for route in detail_routes:
            routes_by_candidate.setdefault(route["entity_id"], []).append(route)
        cls.candidate_ids = sorted(routes_by_candidate)
        cls.projections = {}
        cls.expected_hrefs: dict[str, dict[str, list[str]]] = {}
        cls.rendered: dict[str, dict[str, str]] = {}
        cls.audits: dict[str, dict[str, CandidatePollHTMLAuditParser]] = {}

        if not cls.candidate_ids:
            raise AssertionError("canonical route registry contains no candidates")
        for candidate_id, routes in routes_by_candidate.items():
            languages = {route["language"] for route in routes}
            if languages != {"fr", "en"} or len(routes) != 2:
                raise AssertionError(
                    f"candidate {candidate_id!r} lacks one bilingual route pair"
                )

        for candidate_id in cls.candidate_ids:
            payload = reference.build_projection(
                cls.sources,
                ROOT,
                candidate_id=candidate_id,
                _sources_validated=True,
            )
            observations = payload["polling"]["first_round_history"].get(
                "observations", []
            )
            expected_fr = []
            expected_en = []
            for observation in reversed(observations):
                wave = reference._resolve_poll_history_wave(
                    observation,
                    cls.wave_index,
                    candidate_id=candidate_id,
                )
                expected_fr.append(wave["page_path_fr"])
                expected_en.append(wave["page_path_en"])

            cls.projections[candidate_id] = payload
            cls.expected_hrefs[candidate_id] = {
                "fr": expected_fr,
                "en": expected_en,
            }
            cls.rendered[candidate_id] = {}
            cls.audits[candidate_id] = {}
            for language in ("fr", "en"):
                document = reference.render_html(
                    payload,
                    cls.hud,
                    lang=language,
                    poll_wave_index=cls.wave_index,
                ).decode("utf-8")
                audit = CandidatePollHTMLAuditParser()
                audit.feed(document)
                audit.close()
                cls.rendered[candidate_id][language] = document
                cls.audits[candidate_id][language] = audit

    @staticmethod
    def _valid_wave(
        *,
        wave_id: str = "wave-a",
        slug: str = "wave-a",
        pollster: str = "Example Pollster",
        fieldwork_start: str = "2026-09-15",
        fieldwork_end: str = "2026-09-16",
        sample_size: int = 1000,
        candidate_ids: list[str] | None = None,
    ) -> dict:
        return {
            "wave_id": wave_id,
            "page_slug": slug,
            "page_path_fr": f"/sondages/{slug}/",
            "page_path_en": f"/en/sondages/{slug}/",
            "pollster": pollster,
            "fieldwork_start": fieldwork_start,
            "fieldwork_end": fieldwork_end,
            "sample_size": sample_size,
            "candidate_ids": (
                ["candidate-a"] if candidate_ids is None else candidate_ids
            ),
            "scenario_count": 1,
            "scenarios": [{}],
        }

    @staticmethod
    def _observation(**overrides: object) -> dict:
        observation = {
            "pollster": "Example Pollster",
            "fieldwork_start": "2026-09-15",
            "fieldwork_end": "2026-09-16",
            "sample_size": 1000,
        }
        observation.update(overrides)
        return observation

    @staticmethod
    def _directory_payload(candidate_id: str, observation: dict) -> dict:
        return {
            "candidate_id": candidate_id,
            "polling": {
                "first_round_history": {
                    "observations": [observation],
                }
            },
        }

    def test_every_published_history_observation_resolves_exactly(self) -> None:
        total = 0
        for candidate_id, payload in self.projections.items():
            observations = payload["polling"]["first_round_history"].get(
                "observations", []
            )
            keys = []
            for observation in observations:
                key = reference._poll_history_wave_key(observation)
                keys.append(key)
                wave = reference._resolve_poll_history_wave(
                    observation,
                    self.wave_index,
                    candidate_id=candidate_id,
                )
                self.assertIn(candidate_id, wave["candidate_ids"])
                total += 1
            self.assertEqual(len(keys), len(set(keys)), candidate_id)
        self.assertGreater(total, 0)

    def test_all_rendered_bilingual_href_corpora_are_exact_and_static(self) -> None:
        totals = {"fr": 0, "en": 0}
        expected_total = 0
        for candidate_id, payload in self.projections.items():
            observations = payload["polling"]["first_round_history"].get(
                "observations", []
            )
            expected_total += len(observations)
            for language in ("fr", "en"):
                audit = self.audits[candidate_id][language]
                expected = self.expected_hrefs[candidate_id][language]
                self.assertEqual(audit.hrefs, expected, (candidate_id, language))
                self.assertEqual(
                    len(
                        re.findall(
                            r'<a class="candidate-poll-history-wave-link" '
                            r'href="[^"]+">',
                            self.rendered[candidate_id][language],
                        )
                    ),
                    len(expected),
                    (candidate_id, language),
                )
                totals[language] += len(audit.hrefs)
        self.assertEqual(totals["fr"], expected_total)
        self.assertEqual(totals["en"], expected_total)
        self.assertEqual(totals["fr"], totals["en"])

    def test_every_rendered_href_is_the_matching_canonical_poll_route(self) -> None:
        for candidate_id, expected_by_language in self.expected_hrefs.items():
            for language, hrefs in expected_by_language.items():
                for href in hrefs:
                    with self.subTest(candidate_id=candidate_id, language=language, href=href):
                        route = self.routes_by_path.get(href)
                        self.assertIsNotNone(route)
                        self.assertEqual(route["family"], "polls")
                        self.assertEqual(route["kind"], "poll-wave")
                        self.assertEqual(route["language"], language)
                        self.assertEqual(
                            route["canonical_url"],
                            f"{reference.PUBLIC_ORIGIN}{href}",
                        )

    def test_zero_history_and_directory_placement_contract(self) -> None:
        with_history = 0
        without_history = 0
        for candidate_id, payload in self.projections.items():
            observations = payload["polling"]["first_round_history"].get(
                "observations", []
            )
            if observations:
                with_history += 1
            else:
                without_history += 1
            for language in ("fr", "en"):
                audit = self.audits[candidate_id][language]
                if observations:
                    self.assertEqual(audit.directory_count, 1)
                else:
                    self.assertEqual(audit.directory_count, 0)
                    self.assertEqual(audit.hrefs, [])
                    self.assertNotIn(
                        "candidate-poll-history-directory",
                        self.rendered[candidate_id][language],
                    )
                self.assertEqual(audit.directories_outside_poll_panel, 0)
                self.assertEqual(audit.open_directory_count, 0)
        self.assertEqual(with_history + without_history, len(self.candidate_ids))
        self.assertGreater(with_history, 0)
        self.assertGreater(without_history, 0)

    def test_generated_candidate_pages_have_no_duplicate_element_ids(self) -> None:
        for candidate_id, audits in self.audits.items():
            for language, audit in audits.items():
                duplicates = [
                    element_id
                    for element_id, count in Counter(audit.ids).items()
                    if count > 1
                ]
                self.assertEqual(duplicates, [], (candidate_id, language))

    def test_duplicate_exact_wave_identity_is_rejected(self) -> None:
        first = self._valid_wave()
        second = self._valid_wave(wave_id="wave-b", slug="wave-b")
        with self.assertRaisesRegex(
            reference.CandidateReferenceError,
            "duplicate poll-wave package identity",
        ):
            reference.build_poll_wave_link_index({"waves": [first, second]})

    def test_ballot_label_only_wave_is_not_a_candidate_link_target(self) -> None:
        wave = self._valid_wave(candidate_ids=[])
        wave["scenarios"] = [
            {"candidates": [{"identity_type": "ballot_label"}]}
        ]
        self.assertEqual(
            reference.build_poll_wave_link_index({"waves": [wave]}),
            {},
        )

    def test_missing_mapping_raises_candidate_reference_error(self) -> None:
        observation = self._observation(sample_size=999)
        index = reference.build_poll_wave_link_index(
            {"waves": [self._valid_wave()]}
        )
        with self.assertRaisesRegex(
            reference.CandidateReferenceError,
            "candidate-a.*does not resolve.*999",
        ):
            reference._render_poll_history_link_directory(
                self._directory_payload("candidate-a", observation),
                index,
                lang="fr",
            )

    def test_candidate_membership_mismatch_is_rejected(self) -> None:
        observation = self._observation()
        index = reference.build_poll_wave_link_index(
            {"waves": [self._valid_wave(candidate_ids=["candidate-b"])]}
        )
        with self.assertRaisesRegex(
            reference.CandidateReferenceError,
            "candidate-a.*absent from matched poll wave",
        ):
            reference._render_poll_history_link_directory(
                self._directory_payload("candidate-a", observation),
                index,
                lang="en",
            )

    def test_candidate_link_requirements_are_validated(self) -> None:
        cases = {
            "pollster": {"pollster": ""},
            "fieldwork_start": {"fieldwork_start": "not-a-date"},
            "fieldwork_end": {"fieldwork_end": "2026-02-30"},
            "sample_size": {"sample_size": 0},
            "candidate_ids": {"candidate_ids": []},
            "page_path_fr": {"page_path_fr": "/en/sondages/fr-wrong/"},
            "page_path_en": {"page_path_en": "/sondages/en-wrong/"},
        }
        for field, replacement in cases.items():
            wave = self._valid_wave()
            wave.update(replacement)
            with self.subTest(field=field), self.assertRaisesRegex(
                reference.CandidateReferenceError,
                field,
            ):
                reference.build_poll_wave_link_index({"waves": [wave]})

    def test_missing_and_malformed_explorer_sources_are_wrapped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                reference.CandidateReferenceError,
                "poll explorer source is missing",
            ):
                reference.load_poll_wave_link_index(root)
            (root / "poll_explorer.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(
                reference.CandidateReferenceError,
                "malformed poll explorer JSON",
            ):
                reference.load_poll_wave_link_index(root)

    def test_date_formatter_covers_all_range_shapes_and_punctuation(self) -> None:
        cases = (
            (
                "2026-09-15",
                "2026-09-15",
                "15 sept. 2026",
                "15 Sep 2026",
            ),
            (
                "2026-09-15",
                "2026-09-16",
                "15\u201316 sept. 2026",
                "15\u201316 Sep 2026",
            ),
            (
                "2026-08-31",
                "2026-09-02",
                "31 ao\u00fbt\u20132 sept. 2026",
                "31 Aug\u20132 Sep 2026",
            ),
            (
                "2026-12-31",
                "2027-01-02",
                "31 d\u00e9c. 2026\u20132 janv. 2027",
                "31 Dec 2026\u20132 Jan 2027",
            ),
        )
        for start, end, expected_fr, expected_en in cases:
            with self.subTest(start=start, end=end):
                self.assertEqual(
                    reference._poll_wave_date_label(start, end, lang="fr"),
                    expected_fr,
                )
                self.assertEqual(
                    reference._poll_wave_date_label(start, end, lang="en"),
                    expected_en,
                )
        self.assertEqual(ord("\u2013"), 0x2013)

        wave = self._valid_wave()
        index = reference.build_poll_wave_link_index({"waves": [wave]})
        directory = reference._render_poll_history_link_directory(
            self._directory_payload("candidate-a", self._observation()),
            index,
            lang="fr",
        )
        self.assertIn(" \u00b7 ", directory)
        self.assertEqual(ord("\u00b7"), 0x00B7)

    def test_render_html_uses_alternate_root_poll_explorer(self) -> None:
        candidate_id = min(
            (
                candidate_id
                for candidate_id, payload in self.projections.items()
                if payload["polling"]["first_round_history"].get("observations")
            ),
            key=lambda candidate_id: len(
                self.projections[candidate_id]["polling"]["first_round_history"]
                ["observations"]
            ),
        )
        payload = self.projections[candidate_id]
        observations = payload["polling"]["first_round_history"]["observations"]
        alternate_waves = []
        expected = {"fr": [], "en": []}
        for index, observation in enumerate(observations):
            wave = deepcopy(
                self.wave_index[reference._poll_history_wave_key(observation)]
            )
            slug = f"alternate-root-{index}"
            wave["page_slug"] = slug
            wave["page_path_fr"] = f"/sondages/{slug}/"
            wave["page_path_en"] = f"/en/sondages/{slug}/"
            alternate_waves.append(wave)
            expected["fr"].append(wave["page_path_fr"])
            expected["en"].append(wave["page_path_en"])

        with tempfile.TemporaryDirectory() as directory:
            alternate_root = Path(directory)
            (alternate_root / "poll_explorer.json").write_text(
                json.dumps({"waves": alternate_waves}, ensure_ascii=False),
                encoding="utf-8",
            )
            for language in ("fr", "en"):
                document = reference.render_html(
                    payload,
                    self.hud,
                    lang=language,
                    root=alternate_root,
                ).decode("utf-8")
                audit = CandidatePollHTMLAuditParser()
                audit.feed(document)
                audit.close()
                self.assertEqual(audit.hrefs, list(reversed(expected[language])))

    def test_all_active_build_loads_one_root_aware_wave_index(self) -> None:
        with (
            mock.patch.object(
                reference,
                "load_poll_wave_link_index",
                return_value=self.wave_index,
            ) as load_index,
            mock.patch.object(reference, "render_html", return_value=b"") as render,
        ):
            reference.build_all_active_artifacts(
                self.sources,
                ROOT,
                site_root=ROOT,
            )
        load_index.assert_called_once_with(ROOT)
        self.assertTrue(render.call_args_list)
        self.assertTrue(
            all(
                call.kwargs["poll_wave_index"] is self.wave_index
                for call in render.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
