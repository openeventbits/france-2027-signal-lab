"""Tests for the pinned French Wikipedia candidacy-status collector."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import candidate_candidacy_status
import fetch_candidate_candidacy_status as collector
from candidate_candidacy_status import validate_candidate_candidacy_status
from candidate_identity import candidate_id


TEST_ROOT = Path(__file__).resolve().parent
REVISION_ID = 7654321
REVISION_TIMESTAMP = "2026-08-06T20:48:08Z"


def candidate_table(*names: str, linked: bool = True) -> str:
    rows = []
    for name in names:
        if linked:
            label = f'<a href="/wiki/{candidate_id(name)}">{name}</a>'
        else:
            label = f"<strong>{name}</strong>"
        rows.append(
            "<tr><th>"
            f'<span style="display:none">sort key</span>{label}'
            "<br>(42 ans)<br>Parti test</th><td>Structured data</td></tr>"
        )
    return (
        '<table class="wikitable"><tbody>'
        "<tr><th>Candidat (nom et âge)</th><th>Commentaires</th></tr>"
        + "".join(rows)
        + "</tbody></table>"
    )


def fixture_html(
    *,
    declared_names: tuple[str, ...] = ("Élodie Déclarée",),
    primary_names: tuple[str, ...] = ("François Primaire",),
    prospective_names: tuple[str, ...] = ("Zoë Sans Article",),
    withdrawn_names: tuple[str, ...] = ("Clément Retiré",),
    declined_names: tuple[str, ...] = ("Agnès Déclinée",),
) -> str:
    withdrawn = "".join(
        f'<li><a href="/wiki/{candidate_id(name)}">{name}</a>, ancien mandat.</li>'
        for name in withdrawn_names
    )
    declined = "".join(
        f'<li><a href="/wiki/{candidate_id(name)}">{name}</a> (TEST), fonction.</li>'
        for name in declined_names
    )
    return f"""
    <div class="mw-parser-output">
      <h2>Candidats déclarés</h2>
      {candidate_table(*declared_names)}
      <h3>Candidats déclarés dans le cadre d'une primaire</h3>
      <h4>Primaire de test</h4>
      {candidate_table(*primary_names)}
      <h2>Candidats pressentis</h2>
      {candidate_table(*prospective_names, linked=False)}
      <h2>Candidatures retirées</h2>
      <ul>{withdrawn}</ul>
      <h2>Candidats pressentis ayant décliné</h2>
      <h3>Famille politique</h3>
      <ul>{declined}</ul>
      <h2>Sondages</h2>
      <table><tr><th>Candidat</th></tr><tr><td>Not a candidate row</td></tr></table>
    </div>
    """


def query_response(
    *,
    revision_id: int = REVISION_ID,
    timestamp: str = REVISION_TIMESTAMP,
) -> dict:
    return {
        "query": {
            "pages": [
                {
                    "pageid": 123,
                    "title": collector.PAGE_TITLE,
                    "revisions": [
                        {"revid": revision_id, "timestamp": timestamp}
                    ],
                }
            ]
        }
    }


def parse_response(
    html: str | None = None,
    *,
    revision_id: int = REVISION_ID,
) -> dict:
    return {
        "parse": {
            "title": collector.PAGE_TITLE,
            "pageid": 123,
            "revid": revision_id,
            "text": fixture_html() if html is None else html,
        }
    }


_DEFAULT_RESPONSE = object()


class FakeFetch:
    def __init__(
        self,
        query=_DEFAULT_RESPONSE,
        parsed=_DEFAULT_RESPONSE,
        article_responses=None,
    ):
        self.query = query_response() if query is _DEFAULT_RESPONSE else query
        self.parsed = parse_response() if parsed is _DEFAULT_RESPONSE else parsed
        self.article_responses = article_responses or {}
        self.calls: list[dict[str, str]] = []

    def __call__(self, params):
        copied = dict(params)
        self.calls.append(copied)
        if copied.get("action") == "query" and copied.get("prop") == "revisions":
            return copy.deepcopy(self.query)
        if copied.get("action") == "parse":
            return copy.deepcopy(self.parsed)
        if copied.get("action") == "query" and copied.get("prop") == "info":
            title = copied["titles"]
            response = self.article_responses.get(title)
            if response is None:
                requested_titles = title.split("|")
                response = {
                    "query": {
                        "pages": [
                            {
                                "pageid": 1000 + index,
                                "ns": 0,
                                "title": requested_title,
                            }
                            for index, requested_title in enumerate(
                                requested_titles
                            )
                        ]
                    }
                }
            return copy.deepcopy(response)
        raise AssertionError(f"unexpected MediaWiki action: {copied!r}")


class CandidateExtractionTests(unittest.TestCase):
    def setUp(self):
        self.revision = collector.RevisionSnapshot(
            REVISION_ID,
            REVISION_TIMESTAMP,
        )
        self.payload, self.extracted = collector.build_payload(
            self.revision,
            fixture_html(),
        )
        self.by_name = {
            candidate["candidate_name"]: candidate
            for candidate in self.payload["candidates"]
        }

    def test_declared_candidate_extraction(self):
        candidate = self.by_name["Élodie Déclarée"]
        self.assertEqual(candidate["status"], "declared")
        self.assertEqual(candidate["display_tier"], "main")

    def test_leading_break_before_candidate_name_is_accepted(self):
        standard = candidate_table("Élodie Déclarée")
        leading_break = standard.replace(
            '<th><span style="display:none">sort key</span>',
            "<th><br>",
            1,
        )
        html = fixture_html().replace(standard, leading_break)

        payload, _ = collector.build_payload(self.revision, html)
        by_name = {
            candidate["candidate_name"]: candidate
            for candidate in payload["candidates"]
        }

        self.assertIn("Élodie Déclarée", by_name)
        self.assertEqual(by_name["Élodie Déclarée"]["status"], "declared")

    def test_multiple_leading_breaks_before_candidate_name_fail_closed(self):
        standard = candidate_table("Élodie Déclarée")
        multiple_leading_breaks = standard.replace(
            '<th><span style="display:none">sort key</span>',
            "<th><br><br>",
            1,
        )
        html = fixture_html().replace(
            standard,
            multiple_leading_breaks,
        )

        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "malformed name",
        ):
            collector.build_payload(self.revision, html)

    def test_primary_contender_extraction(self):
        candidate = self.by_name["François Primaire"]
        self.assertEqual(candidate["status"], "primary_contender")
        self.assertEqual(candidate["display_tier"], "main")

    def test_prospective_candidate_extraction(self):
        candidate = self.by_name["Zoë Sans Article"]
        self.assertEqual(candidate["status"], "active_potential")
        self.assertEqual(candidate["display_tier"], "secondary")

    def test_withdrawn_candidate_extraction(self):
        candidate = self.by_name["Clément Retiré"]
        self.assertEqual(candidate["status"], "withdrawn")
        self.assertEqual(candidate["display_tier"], "hidden")

    def test_declined_candidate_extraction_under_family_subsection(self):
        candidate = self.by_name["Agnès Déclinée"]
        self.assertEqual(candidate["status"], "ruled_out")
        self.assertEqual(candidate["display_tier"], "hidden")

    def test_nested_primary_table_is_not_double_counted_as_declared(self):
        primary = [
            item
            for item in self.payload["candidates"]
            if item["candidate_name"] == "François Primaire"
        ]
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0]["status"], "primary_contender")

    def test_candidate_without_personal_article_survives(self):
        extracted = {
            item.candidate_name: item for item in self.extracted
        }
        self.assertFalse(extracted["Zoë Sans Article"].has_personal_article)
        self.assertIn("Zoë Sans Article", self.by_name)
        self.assertIsNone(
            self.by_name["Zoë Sans Article"]["wikipedia_article"]
        )

    def test_candidate_ids_reuse_shared_identity_logic(self):
        for name, candidate in self.by_name.items():
            with self.subTest(name=name):
                self.assertEqual(candidate["candidate_id"], candidate_id(name))

    def test_accents_normalize_to_ascii_ids(self):
        self.assertEqual(
            self.by_name["Élodie Déclarée"]["candidate_id"],
            "elodie-declaree",
        )
        self.assertEqual(
            self.by_name["Agnès Déclinée"]["candidate_id"],
            "agnes-declinee",
        )

    def test_duplicate_id_collision_fails_closed(self):
        html = fixture_html(
            primary_names=("Łukasz Test",),
            prospective_names=("ukasz Test",),
        )
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "candidate id collision",
        ):
            collector.build_payload(self.revision, html)

    def test_same_person_in_conflicting_sections_fails_closed(self):
        html = fixture_html(primary_names=("Élodie Déclarée",))
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "conflicting semantic categories",
        ):
            collector.build_payload(self.revision, html)

    def test_malformed_candidate_name_fails_closed(self):
        malformed = candidate_table("Valid Candidate").replace(
            '<a href="/wiki/valid-candidate">Valid Candidate</a>',
            "",
        )
        html = fixture_html().replace(
            candidate_table("Élodie Déclarée"),
            malformed,
        )
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "malformed name",
        ):
            collector.build_payload(self.revision, html)

    def test_missing_required_section_fails_closed(self):
        html = fixture_html().replace(
            "<h2>Candidatures retirées</h2>",
            "<h2>Section supprimée</h2>",
        )
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "required semantic sections are missing",
        ):
            collector.build_payload(self.revision, html)

    def test_empty_candidate_set_fails_closed(self):
        html = fixture_html(
            declared_names=(),
            primary_names=(),
            prospective_names=(),
            withdrawn_names=(),
            declined_names=(),
        )
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "no candidates",
        ):
            collector.build_payload(self.revision, html)

    def test_no_active_candidates_fails_closed(self):
        html = fixture_html(
            declared_names=(),
            primary_names=(),
            prospective_names=(),
        )
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "no active candidates",
        ):
            collector.build_payload(self.revision, html)

    def test_dynamic_candidate_total_validates(self):
        self.assertEqual(len(self.payload["candidates"]), 5)
        validate_candidate_candidacy_status(self.payload)

    def test_arbitrary_main_secondary_hidden_counts_validate(self):
        html = fixture_html(
            declared_names=("Alpha Main", "Beta Main"),
            primary_names=(),
            prospective_names=("Gamma Secondary", "Delta Secondary"),
            withdrawn_names=("Epsilon Hidden", "Eta Hidden"),
            declined_names=("Theta Hidden",),
        )
        payload, _ = collector.build_payload(self.revision, html)
        counts = {
            tier: sum(
                item["display_tier"] == tier
                for item in payload["candidates"]
            )
            for tier in ("main", "secondary", "hidden")
        }
        self.assertEqual(counts, {"main": 2, "secondary": 2, "hidden": 3})

    def test_old_fixed_snapshot_assumptions_are_absent(self):
        source = Path(candidate_candidacy_status.__file__).read_text(
            encoding="utf-8"
        )
        for obsolete in (
            "_EXPECTED_TOTAL",
            "_EXPECTED_TIER_COUNTS",
            "_EXPECTED_HIDDEN_IDS",
            "exactly 20 entries",
            "complete 20-person coverage",
            "current hidden candidate IDs",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, source)

    def test_exact_revision_permanent_url_is_emitted(self):
        urls = {item["source_url"] for item in self.payload["candidates"]}
        self.assertEqual(urls, {self.revision.permanent_url})
        self.assertIn(f"oldid={REVISION_ID}", self.revision.permanent_url)
        self.assertEqual(self.payload["status_as_of"], "2026-08-06")
        self.assertTrue(
            all(item["source_date"] == "2026-08-06" for item in self.payload["candidates"])
        )


class MediaWikiApiTests(unittest.TestCase):
    def test_canonical_source_is_dedicated_candidatures_page(self):
        self.assertEqual(
            collector.PAGE_TITLE,
            "Candidatures à l'élection présidentielle française de 2027",
        )

        fake = FakeFetch()
        collector.fetch_candidate_candidacy_status(fake)

        self.assertEqual(
            fake.calls[0]["titles"],
            "Candidatures à l'élection présidentielle française de 2027",
        )

    def test_revision_metadata_then_exact_oldid_parse(self):
        fake = FakeFetch()
        result = collector.fetch_candidate_candidacy_status(fake)
        self.assertEqual(result.revision.revision_id, REVISION_ID)
        self.assertEqual(result.revision.revision_timestamp, REVISION_TIMESTAMP)
        self.assertEqual(
            [call["action"] for call in fake.calls[:2]],
            ["query", "parse"],
        )
        self.assertTrue(
            all(call.get("prop") == "info" for call in fake.calls[2:])
        )
        self.assertEqual(
            sum(call.get("prop") == "info" for call in fake.calls),
            1,
        )
        self.assertEqual(fake.calls[1]["oldid"], str(REVISION_ID))
        self.assertNotIn("page", fake.calls[1])

    def test_post_revision_failure_reports_exact_revision(self):
        malformed_html = "<h2>Unexpected structure</h2>"
        fake = FakeFetch(parsed=parse_response(malformed_html))

        with self.assertRaises(
            collector.CandidateCandidacyFetchError
        ) as context:
            collector.fetch_candidate_candidacy_status(fake)

        message = str(context.exception)
        self.assertIn(
            f"Wikipedia revision {REVISION_ID}",
            message,
        )
        self.assertIn(REVISION_TIMESTAMP, message)
        self.assertIn(
            "required semantic sections are missing",
            message,
        )

    def test_revision_only_refresh_reports_no_semantic_change(self):
        previous = collector.fetch_candidate_candidacy_status(
            FakeFetch()
        ).payload
        next_revision = REVISION_ID + 1
        fake = FakeFetch(
            query=query_response(
                revision_id=next_revision,
                timestamp="2026-08-07T04:05:00Z",
            ),
            parsed=parse_response(revision_id=next_revision),
        )
        result = collector.fetch_candidate_candidacy_status(
            fake,
            previous_registry=previous,
        )
        self.assertFalse(result.semantic_changed)

    def test_curated_first_party_evidence_overrides_wikipedia_status(self):
        name = "Élodie Déclarée"
        curated = collector.CuratedCandidacySource(
            source_id="elodie-official",
            candidate_id=collector.candidate_id(name),
            candidate_name=name,
            source_type="candidate_first_party",
            publisher="Official campaign",
            url="https://unit-fixture.fr/elodie-2027",
            source_date="2026-08-07",
            source_title="Official candidacy update",
            status="withdrawn",
            status_as_of="2026-08-07",
            status_note="Officially announced withdrawal.",
        )

        result = collector.fetch_candidate_candidacy_status(
            FakeFetch(),
            curated_sources=(curated,),
        )
        candidate = next(
            row for row in result.payload["candidates"]
            if row["candidate_name"] == name
        )

        self.assertEqual(candidate["status"], "withdrawn")
        self.assertEqual(candidate["display_tier"], "hidden")
        self.assertEqual(candidate["source_publisher"], "Official campaign")
        self.assertEqual(candidate["source_url"], "https://unit-fixture.fr/elodie-2027")
        self.assertEqual(result.payload["status_as_of"], "2026-08-07")

    def test_stale_curated_evidence_cannot_rollback_last_good_status(self):
        name = "Élodie Déclarée"
        identifier = collector.candidate_id(name)
        newer = collector.CuratedCandidacySource(
            source_id="elodie-newer",
            candidate_id=identifier,
            candidate_name=name,
            source_type="candidate_first_party",
            publisher="Official campaign",
            url="https://unit-fixture.fr/elodie-newer",
            source_date="2026-08-08",
            source_title="Newer official candidacy update",
            status="withdrawn",
            status_as_of="2026-08-08",
            status_note="Officially announced withdrawal.",
        )
        previous = collector.fetch_candidate_candidacy_status(
            FakeFetch(),
            curated_sources=(newer,),
        ).payload

        stale = collector.CuratedCandidacySource(
            source_id="elodie-stale",
            candidate_id=identifier,
            candidate_name=name,
            source_type="candidate_first_party",
            publisher="Older official page",
            url="https://unit-fixture.fr/elodie-stale",
            source_date="2026-08-07",
            source_title="Older candidacy page",
            status="declared",
            status_as_of="2026-08-07",
            status_note="Previously described as a candidate.",
        )
        result = collector.fetch_candidate_candidacy_status(
            FakeFetch(),
            previous_registry=previous,
            curated_sources=(stale,),
        )
        candidate = next(
            row for row in result.payload["candidates"]
            if row["candidate_name"] == name
        )

        self.assertEqual(candidate["status"], "withdrawn")
        self.assertEqual(candidate["display_tier"], "hidden")
        self.assertEqual(candidate["source_publisher"], "Official campaign")
        self.assertEqual(candidate["source_url"], "https://unit-fixture.fr/elodie-newer")
        self.assertEqual(candidate["status_as_of"], "2026-08-08")


    def test_malformed_api_payload_fails_closed(self):
        for malformed in (None, {}, {"query": {}}, {"query": {"pages": []}}):
            with self.subTest(malformed=malformed):
                with self.assertRaises(collector.CandidateCandidacyFetchError):
                    collector.fetch_current_revision(lambda _params: malformed)

    def test_malformed_parse_payload_fails_closed(self):
        for malformed in (None, {}, {"parse": {}}, {"parse": {"text": "x"}}):
            with self.subTest(malformed=malformed):
                fake = FakeFetch(parsed=malformed)
                with self.assertRaises(collector.CandidateCandidacyFetchError):
                    collector.fetch_candidate_candidacy_status(fake)

    def test_missing_revision_id_fails_closed(self):
        response = query_response()
        del response["query"]["pages"][0]["revisions"][0]["revid"]
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "revision response|revision ID",
        ):
            collector.fetch_current_revision(lambda _params: response)

    def test_missing_revision_timestamp_fails_closed(self):
        response = query_response()
        del response["query"]["pages"][0]["revisions"][0]["timestamp"]
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "revision response|revision timestamp",
        ):
            collector.fetch_current_revision(lambda _params: response)

    def test_invalid_revision_timestamp_fails_closed(self):
        response = query_response(timestamp="2026-02-30T20:48:08Z")
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "timestamp is invalid",
        ):
            collector.fetch_current_revision(lambda _params: response)

    def test_parse_revision_mismatch_fails_closed(self):
        fake = FakeFetch(parsed=parse_response(revision_id=REVISION_ID + 1))
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "does not match requested oldid",
        ):
            collector.fetch_candidate_candidacy_status(fake)


class CommandLineTests(unittest.TestCase):
    def test_previous_defaults_to_tracked_registry_path(self):
        args = collector._parser().parse_args(["--output", "result.json"])
        self.assertFalse(args.no_previous)
        self.assertEqual(args.previous, collector.DEFAULT_PREVIOUS_PATH)

    def test_explicit_no_previous_mode(self):
        args = collector._parser().parse_args(
            ["--output", "result.json", "--no-previous"]
        )
        self.assertTrue(args.no_previous)


class SerializationAndWriteTests(unittest.TestCase):
    def setUp(self):
        revision = collector.RevisionSnapshot(REVISION_ID, REVISION_TIMESTAMP)
        self.payload, _ = collector.build_payload(revision, fixture_html())

    def test_serialization_is_deterministic(self):
        first = collector.serialize_payload(self.payload)
        second = collector.serialize_payload(copy.deepcopy(self.payload))
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertEqual(json.loads(first), self.payload)

    def test_output_is_not_written_when_validation_fails(self):
        invalid = copy.deepcopy(self.payload)
        invalid["candidates"] = []
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as directory:
            output = Path(directory) / "registry.json"
            output.write_text("last-good\n", encoding="utf-8")
            with self.assertRaises(collector.CandidateCandidacyFetchError):
                collector.write_payload_atomic(invalid, output)
            self.assertEqual(output.read_text(encoding="utf-8"), "last-good\n")
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_successful_output_is_written_atomically(self):
        real_replace = os.replace
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as directory:
            output = Path(directory) / "registry.json"
            with mock.patch.object(
                collector.os,
                "replace",
                side_effect=real_replace,
            ) as replace:
                collector.write_payload_atomic(self.payload, output)
            replace.assert_called_once()
            temporary, destination = map(Path, replace.call_args.args)
            self.assertEqual(temporary.parent, output.parent)
            self.assertEqual(destination, output)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                collector.serialize_payload(self.payload),
            )
            self.assertEqual(list(Path(directory).iterdir()), [output])


if __name__ == "__main__":
    unittest.main()
