"""Contract tests for supplemental Candidate Universe sources."""

from __future__ import annotations

import unittest

import fetch_candidate_candidacy_status as collector


def extracted(name: str, section: str) -> collector.ExtractedCandidate:
    return collector.ExtractedCandidate(
        candidate_name=name,
        section_title=section,
        requested_article_title=name,
    )



def socialist_candidate_table(name: str) -> str:
    slug = name.replace(" ", "_")
    return (
        '<table class="wikitable"><tbody>'
        '<tr><th>Candidat (nom et âge)</th><th>Commentaires</th></tr>'
        '<tr><th>'
        f'<span style="display:none">sort key</span>'
        f'<a href="/wiki/{slug}">{name}</a>'
        '<br>(42 ans)<br>Parti test'
        '</th><td>Structured data</td></tr>'
        '</tbody></table>'
    )


def socialist_fixture_html() -> str:
    return f"""
    <div class="mw-parser-output">
      <h2>Candidats officiels</h2>
      {socialist_candidate_table("Olivier Faure")}
      <h2>Candidatures n'ayant pas abouti</h2>
      <ul>
        <li><a href="/wiki/Philippe_Brun">Philippe Brun</a>, candidature non aboutie.</li>
        <li><strong>Fabien Verdier</strong>, candidature non aboutie.</li>
      </ul>
      <h2>Candidats ayant décliné</h2>
      <ul>
        <li><a href="/wiki/Anne_Hidalgo">Anne Hidalgo</a>, candidature déclinée.</li>
      </ul>
    </div>
    """


class SupplementalCandidateSourceContractTests(unittest.TestCase):
    def test_socialist_primary_page_is_explicitly_configured(self):
        self.assertEqual(
            collector.SOCIALIST_PRIMARY_PAGE_TITLE,
            "Primaire présidentielle socialiste française de 2026",
        )

    def test_socialist_primary_section_semantics_are_narrow(self):
        rules = collector.SOCIALIST_PRIMARY_SECTION_RULES

        self.assertEqual(
            set(rules),
            {
                "Candidats officiels",
                "Candidatures n'ayant pas abouti",
            },
        )

        official = rules["Candidats officiels"]
        self.assertEqual(official.status, "primary_contender")
        self.assertEqual(official.display_tier, "main")
        self.assertEqual(official.structured_kind, "table")

        unsuccessful = rules["Candidatures n'ayant pas abouti"]
        self.assertEqual(unsuccessful.status, "ruled_out")
        self.assertEqual(unsuccessful.display_tier, "hidden")
        self.assertEqual(unsuccessful.structured_kind, "list")



    def test_supplemental_revision_snapshot_uses_its_own_page_title(self):
        snapshot = collector.RevisionSnapshot(
            987654,
            "2026-09-16T12:00:00Z",
            page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )

        self.assertEqual(
            snapshot.page_title,
            collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )
        self.assertIn("oldid=987654", snapshot.permanent_url)
        self.assertIn(
            "title=Primaire+pr%C3%A9sidentielle+socialiste+"
            "fran%C3%A7aise+de+2026",
            snapshot.permanent_url,
        )

    def test_fetch_current_revision_queries_requested_page_title(self):
        calls = []

        def fake_fetch(params):
            calls.append(dict(params))
            return {
                "query": {
                    "pages": [
                        {
                            "pageid": 321,
                            "title": collector.SOCIALIST_PRIMARY_PAGE_TITLE,
                            "revisions": [
                                {
                                    "revid": 987654,
                                    "timestamp": "2026-09-16T12:00:00Z",
                                }
                            ],
                        }
                    ]
                }
            }

        snapshot = collector.fetch_current_revision(
            fake_fetch,
            page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )

        self.assertEqual(
            calls[0]["titles"],
            collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )
        self.assertEqual(
            snapshot.page_title,
            collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )

    def test_fetch_parsed_revision_accepts_requested_page_title(self):
        calls = []

        def fake_fetch(params):
            calls.append(dict(params))
            return {
                "parse": {
                    "title": collector.SOCIALIST_PRIMARY_PAGE_TITLE,
                    "pageid": 321,
                    "revid": 987654,
                    "text": "<div>supplemental fixture</div>",
                }
            }

        html = collector.fetch_parsed_revision(
            987654,
            fake_fetch,
            page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )

        self.assertEqual(html, "<div>supplemental fixture</div>")
        self.assertEqual(calls[0]["oldid"], "987654")
        self.assertNotIn("page", calls[0])

    def test_fetch_parsed_revision_rejects_wrong_source_title(self):
        def fake_fetch(params):
            return {
                "parse": {
                    "title": collector.PAGE_TITLE,
                    "pageid": 123,
                    "revid": 987654,
                    "text": "<div>wrong page</div>",
                }
            }

        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "does not match configured page",
        ):
            collector.fetch_parsed_revision(
                987654,
                fake_fetch,
                page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
            )

    def test_socialist_parser_uses_source_specific_rules(self):
        candidates = collector.extract_candidates(
            socialist_fixture_html(),
            section_rules=collector.SOCIALIST_PRIMARY_SECTION_RULES,
            source_page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )

        by_name = {
            candidate.candidate_name: candidate
            for candidate in candidates
        }

        self.assertEqual(
            set(by_name),
            {
                "Olivier Faure",
                "Philippe Brun",
                "Fabien Verdier",
            },
        )
        self.assertTrue(
            all(
                candidate.source_page_title
                == collector.SOCIALIST_PRIMARY_PAGE_TITLE
                for candidate in candidates
            )
        )
        self.assertEqual(
            collector.section_rule_for_candidate(
                by_name["Olivier Faure"]
            ).status,
            "primary_contender",
        )
        self.assertEqual(
            collector.section_rule_for_candidate(
                by_name["Philippe Brun"]
            ).status,
            "ruled_out",
        )
        self.assertEqual(
            collector.section_rule_for_candidate(
                by_name["Fabien Verdier"]
            ).status,
            "ruled_out",
        )

    def test_socialist_parser_missing_required_section_fails_closed(self):
        html = socialist_fixture_html().replace(
            "<h2>Candidatures n'ayant pas abouti</h2>",
            "<h2>Section supprimée</h2>",
        )

        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "required semantic sections are missing",
        ):
            collector.extract_candidates(
                html,
                section_rules=collector.SOCIALIST_PRIMARY_SECTION_RULES,
                source_page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
            )

    def test_candidate_remembers_main_source_identity(self):
        candidate = collector.ExtractedCandidate(
            candidate_name="Candidate Principal",
            section_title="Candidats déclarés",
            requested_article_title="Candidate Principal",
            source_page_title=collector.PAGE_TITLE,
        )

        rule = collector.section_rule_for_candidate(candidate)

        self.assertEqual(candidate.source_page_title, collector.PAGE_TITLE)
        self.assertEqual(rule.status, "declared")
        self.assertEqual(rule.display_tier, "main")

    def test_socialist_official_heading_has_source_specific_semantics(self):
        candidate = collector.ExtractedCandidate(
            candidate_name="Olivier Faure",
            section_title="Candidats officiels",
            requested_article_title="Olivier Faure",
            source_page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )

        rule = collector.section_rule_for_candidate(candidate)

        self.assertEqual(rule.status, "primary_contender")
        self.assertEqual(rule.display_tier, "main")

    def test_socialist_unsuccessful_heading_has_source_specific_semantics(self):
        candidate = collector.ExtractedCandidate(
            candidate_name="Philippe Brun",
            section_title="Candidatures n'ayant pas abouti",
            requested_article_title="Philippe Brun",
            source_page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )

        rule = collector.section_rule_for_candidate(candidate)

        self.assertEqual(rule.status, "ruled_out")
        self.assertEqual(rule.display_tier, "hidden")

    def test_merge_preserves_supplemental_source_identity(self):
        supplemental_candidate = collector.ExtractedCandidate(
            candidate_name="Philippe Brun",
            section_title="Candidatures n'ayant pas abouti",
            requested_article_title="Philippe Brun",
            source_page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )

        merged = collector.merge_candidate_extractions(
            [],
            [supplemental_candidate],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0].source_page_title,
            collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )


    def test_known_supplemental_candidate_uses_current_source_semantics(self):
        candidate = collector.ExtractedCandidate(
            candidate_name="Philippe Brun",
            section_title="Candidatures n'ayant pas abouti",
            requested_article_title="Philippe Brun",
            source_page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )
        previous = {
            "candidate_id": "philippe-brun",
            "candidate_name": "Philippe Brun",
            "status": "primary_contender",
            "display_tier": "main",
            "status_note": "Previously accepted primary-contender evidence.",
        }

        rule = collector.effective_rule_for_candidate(
            candidate,
            previous,
        )

        self.assertEqual(rule.status, "ruled_out")
        self.assertEqual(rule.display_tier, "hidden")

    def test_primary_candidate_uses_current_primary_semantics(self):
        candidate = collector.ExtractedCandidate(
            candidate_name="Candidate Principal",
            section_title="Candidats déclarés",
            requested_article_title="Candidate Principal",
            source_page_title=collector.PAGE_TITLE,
        )
        previous = {
            "candidate_id": "candidate-principal",
            "candidate_name": "Candidate Principal",
            "status": "active_potential",
            "display_tier": "secondary",
            "status_note": "Older evidence.",
        }

        rule = collector.effective_rule_for_candidate(
            candidate,
            previous,
        )

        self.assertEqual(rule.status, "declared")
        self.assertEqual(rule.display_tier, "main")

    def test_new_supplemental_identity_is_not_admitted_by_build_policy(self):
        candidate = collector.ExtractedCandidate(
            candidate_name="Nouvelle Candidate",
            section_title="Candidats officiels",
            requested_article_title="Nouvelle Candidate",
            source_page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        )

        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "supplemental source cannot create a new candidate identity",
        ):
            collector.effective_rule_for_candidate(
                candidate,
                None,
            )

    def test_supplemental_only_identity_is_added(self):
        primary = [
            extracted("Candidate Principal", "Candidats déclarés"),
        ]
        supplemental = [
            extracted("Philippe Brun", "Candidats déclarés"),
        ]

        merged = collector.merge_candidate_extractions(
            primary,
            supplemental,
        )

        self.assertEqual(
            [candidate.candidate_name for candidate in merged],
            ["Candidate Principal", "Philippe Brun"],
        )

    def test_primary_source_wins_for_duplicate_identity(self):
        primary_candidate = extracted(
            "Carole Delga",
            "Candidats pressentis ayant décliné",
        )
        supplemental_candidate = extracted(
            "Carole Delga",
            "Candidats pressentis",
        )

        merged = collector.merge_candidate_extractions(
            [primary_candidate],
            [supplemental_candidate],
        )

        self.assertEqual(len(merged), 1)
        self.assertIs(merged[0], primary_candidate)


if __name__ == "__main__":
    unittest.main()
