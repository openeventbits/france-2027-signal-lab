import copy
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import build_candidate_signals as builder
from candidate_identity import (
    CandidateIdentityError,
    candidate_id,
    candidate_identity_map,
    canonical_candidate_name,
    canonicalize_candidate_roster,
    normalized_candidate_key,
)


ROOT = Path(__file__).resolve().parent



def poll_event(
    *,
    pollster="Alpha",
    fieldwork_start="2026-07-09",
    fieldwork_end="2026-07-10",
    publication_date=None,
    sample_size=1000,
    scenario_key="scenario",
    event_id=None,
    candidates=None,
    source_url=None,
):
    if candidates is None:
        candidates = [("Candidate A", 60), ("Candidate B", 40)]
    public_candidates = [
        {"name": name, "score": score}
        for name, score in candidates
    ]
    numeric_scores = [
        score
        for _name, score in candidates
        if isinstance(score, (int, float)) and not isinstance(score, bool)
    ]
    total = sum(numeric_scores)
    complete = len(numeric_scores) == len(candidates) and 99 <= total <= 101
    value = {
        "event_id": event_id
        or f"{pollster}-{fieldwork_start}-{fieldwork_end}-{sample_size}-{scenario_key}",
        "pollster": pollster,
        "fieldwork_start": fieldwork_start,
        "fieldwork_end": fieldwork_end,
        "round": "first_round",
        "hypothesis": scenario_key,
        "scenario_key": scenario_key,
        "sample_size": sample_size,
        "source_url": source_url
        or f"https://polls.example/{pollster}/{sample_size}/{scenario_key}",
        "candidates": public_candidates,
        "reported_total": total,
        "completeness_status": "complete" if complete else "partial",
        "partial_scenario": not complete,
        "unreported_share": None if complete else 100 - total,
    }
    if publication_date is not None:
        value["publication_date"] = publication_date
    return value


def concentration(record_count=1):
    return {
        "leading_publisher": "Publisher",
        "leading_publisher_record_count": record_count,
        "leading_publisher_share": 1.0,
        "leading_story_record_count": record_count,
        "leading_story_share": 1.0,
    }


def visibility_metric(name, lane, record_count=1):
    if lane == "primary":
        scope_counts = {
            "election": record_count,
            "campaign": 0,
            "general": 0,
        }
        scope_shares = {
            "election": 1.0,
            "campaign": 0.0,
            "general": 0.0,
        }
    else:
        scope_counts = {
            "election": 0,
            "campaign": 0,
            "general": record_count,
        }
        scope_shares = {
            "election": 0.0,
            "campaign": 0.0,
            "general": 1.0,
        }
    return {
        "candidate": name,
        "record_count": record_count,
        "share": 1.0,
        "publisher_count": 1,
        "publisher_names": ["Publisher"],
        "active_day_count": 1,
        "headline_match_count": record_count,
        "summary_only_match_count": 0,
        "scope_counts": scope_counts,
        "scope_shares": scope_shares,
        "story_cluster_count": 1,
        "story_clusters": [{"cluster_id": "not-copied"}],
        "concentration": concentration(record_count),
    }


def visibility_period(start, end, metrics):
    record_count = sum(metric["record_count"] for metric in metrics)
    return {
        "start_date": start,
        "end_date": end,
        "record_count": record_count,
        "publisher_count": 1 if metrics else 0,
        "publisher_names": ["Publisher"] if metrics else [],
        "candidate_metrics": metrics,
    }


def news_fixture(
    *,
    generated_at="2026-07-29T08:00:00Z",
    primary_metrics=None,
    general_metrics=None,
    candidate_watch=None,
    roster_names=None,
):
    primary_metrics = (
        [visibility_metric("Candidate A", "primary")]
        if primary_metrics is None
        else primary_metrics
    )
    general_metrics = (
        [visibility_metric("Candidate A", "general")]
        if general_metrics is None
        else general_metrics
    )
    candidate_watch = [] if candidate_watch is None else candidate_watch
    roster_names = (
        ["Candidate A", "Candidate B"]
        if roster_names is None
        else roster_names
    )
    current = visibility_period(
        "2026-07-23",
        "2026-07-29",
        primary_metrics,
    )
    prior = visibility_period(
        "2026-07-16",
        "2026-07-22",
        [],
    )
    general_current = visibility_period(
        "2026-07-23",
        "2026-07-29",
        general_metrics,
    )
    general_prior = visibility_period(
        "2026-07-16",
        "2026-07-22",
        [],
    )
    quality = {
        "status": "not_comparable",
        "reason": "insufficient_data",
        "current_record_count": current["record_count"],
        "prior_record_count": prior["record_count"],
        "current_publisher_count": current["publisher_count"],
        "prior_publisher_count": prior["publisher_count"],
        "common_publisher_count": 0,
        "publisher_union_count": current["publisher_count"],
        "publisher_overlap_ratio": 0.0,
        "record_count_ratio": None,
        "thresholds": {
            "minimum_period_records": 10,
            "minimum_period_publishers": 5,
            "minimum_common_publishers": 5,
            "minimum_publisher_overlap_ratio": 0.5,
            "maximum_record_count_ratio": 2.0,
        },
    }
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "candidate_roster": {
            "rule": "fixture",
            "cutoff_date": "2026-01-27",
            "count": len(roster_names),
            "names": roster_names,
        },
        "candidate_visibility": {
            "method": "share_of_candidate_linked_records",
            "primary_scopes": ["election", "campaign"],
            "secondary_scope": "general",
            "current_period": current,
            "prior_period": prior,
            "general_current_period": general_current,
            "general_prior_period": general_prior,
            "comparison_quality": quality,
        },
        "candidate_watch": candidate_watch,
    }


def association(name, relationship):
    return {
        "candidate_id": candidate_id(name),
        "candidate_name": name,
        "relationship": relationship,
    }


def review(review_id, review_date, associations):
    return {
        "id": review_id,
        "review_url": f"https://reviews.example/{review_id}",
        "review_date": review_date,
        "candidate_associations": associations,
    }


def claims_fixture(
    *,
    generated_at="2026-07-27T08:00:00Z",
    reviews=None,
):
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "candidate_window_days": 45,
        "archive_window_days": 365,
        "candidate_roster": {"count": 0, "candidates": []},
        "counts": {},
        "reviews": [] if reviews is None else reviews,
    }


def candidate_match(candidate, *locations):
    return {
        "candidate": candidate,
        "matched_aliases": [candidate],
        "locations": list(locations),
    }


def watch_item(
    item_id,
    published_at,
    scope,
    *,
    candidate="Candidate A",
    url=None,
    candidate_matches=None,
):
    if candidate_matches is None:
        candidate_matches = [
            candidate_match(candidate, "headline")
        ]

    return {
        "id": item_id,
        "publisher": "Publisher",
        "published_at": published_at,
        "headline": item_id,
        "url": (
            f"https://news.example/{item_id}"
            if url is None
            else url
        ),
        "explicit_election": scope == "election",
        "candidates": [
            match["candidate"]
            for match in candidate_matches
        ],
        "candidate_matches": candidate_matches,
        "coverage_scope": scope,
    }


def candidate_records(*names):
    return [
        {
            "candidate_id": candidate_id(name),
            "candidate_name": name,
        }
        for name in sorted(names, key=lambda value: (value.casefold(), candidate_id(value)))
    ]


def expected_featured_board_rows(
    selected_event,
    registry_candidates,
    display_limit,
):
    registry_by_name = {
        candidate["candidate_name"]: candidate
        for candidate in registry_candidates
    }
    registry_names = list(registry_by_name)
    rows = []
    for source_position, candidate in enumerate(
        selected_event["candidates"],
        start=1,
    ):
        resolved_name = builder.resolve_candidate_name(
            candidate["name"],
            registry_names,
        )
        registry_candidate = registry_by_name[resolved_name]
        rows.append(
            {
                "candidate_id": registry_candidate["candidate_id"],
                "candidate_name": registry_candidate["candidate_name"],
                "reported_score": candidate["score"],
                "source_position": source_position,
            }
        )
    ordered = sorted(rows, key=builder._featured_poll_candidate_sort_key)
    return [
        {**row, "display_position": display_position}
        for display_position, row in enumerate(ordered[:display_limit], start=1)
    ]


def featured_poll_board_fixture():
    names = [f"Candidate {letter}" for letter in "ABCDEFGHIJKL"]
    registry = candidate_records(*names)
    selected_candidates = list(
        zip(
            names,
            [3, 20, 10, 10, 15, 12, 9, 8, 6, 4, 2, 1],
            strict=True,
        )
    )
    selected = poll_event(
        pollster="Alpha",
        sample_size=1200,
        scenario_key="selected-scenario",
        event_id="selected-event",
        candidates=selected_candidates,
    )
    alternate_scores = {"Candidate B": 30, "Candidate E": 5}
    alternate = poll_event(
        pollster="Alpha",
        sample_size=1200,
        scenario_key="alternate-scenario",
        event_id="alternate-event",
        candidates=[
            (name, alternate_scores.get(name, score))
            for name, score in selected_candidates
        ],
    )
    cross_poll = poll_event(
        pollster="Beta",
        sample_size=1200,
        scenario_key="cross-poll-scenario",
        event_id="cross-poll-event",
        candidates=[("Candidate A", 60), ("Candidate B", 40)],
    )
    packages = builder.build_poll_packages([selected, alternate, cross_poll])
    package = next(
        package
        for package in packages
        if package["pollster"] == "Alpha"
    )
    public_package = builder._featured_package_public(package)
    board = builder._featured_poll_board_public(
        package,
        registry,
        public_package["source_urls"],
    )
    return {
        "package": package,
        "selected_event": selected,
        "cross_poll_event": cross_poll,
        "board": board,
    }


class IdentityTests(unittest.TestCase):
    def test_accented_names_keep_display_and_make_ascii_ids(self):
        examples = {
            "Gabriel Attal": "gabriel-attal",
            "Jean-Luc Mélenchon": "jean-luc-melenchon",
            "Édouard Philippe": "edouard-philippe",
            "Raphaël Glucksmann": "raphael-glucksmann",
        }
        for name, expected in examples.items():
            with self.subTest(name=name):
                self.assertEqual(canonical_candidate_name(name), name)
                self.assertEqual(candidate_id(name), expected)

    def test_whitespace_and_accent_normalization(self):
        self.assertEqual(
            canonical_candidate_name("  Jean-Luc\tMélenchon  "),
            "Jean-Luc Mélenchon",
        )
        self.assertEqual(
            normalized_candidate_key("Édouard  Philippe"),
            "edouard philippe",
        )

    def test_identity_and_id_collisions_are_rejected(self):
        for names in (
            ["Éric Zemmour", "Eric Zemmour"],
            ["Jean Luc", "Jean-Luc"],
        ):
            with self.subTest(names=names):
                with self.assertRaises(CandidateIdentityError):
                    candidate_identity_map(names)

    def test_short_labels_do_not_infer_candidate_identity(self):
        self.assertEqual(
            canonicalize_candidate_roster(
                ["Attal", "Gabriel Attal", "Philippe", "Édouard Philippe"]
            ),
            ["Attal", "Gabriel Attal", "Philippe", "Édouard Philippe"],
        )
        self.assertEqual(
            canonicalize_candidate_roster(
                ["Martin", "Alice Martin", "Bob Martin"]
            ),
            ["Alice Martin", "Bob Martin", "Martin"],
        )


class CandidateUniverseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.polls, cls.news, cls.claims, cls.candidacy_status = builder.load_inputs(
            ROOT / "polls.json",
            ROOT / "news_wire.json",
            ROOT / "claims_under_scrutiny.json",
            ROOT / "candidate_candidacy_status.json",
        )

    def test_current_registry_is_complete_candidate_universe(self):
        universe, candidates = builder.candidate_universe_from_candidacy_status(
            self.candidacy_status
        )
        self.assertEqual(
            universe,
            {
                "source": "candidate_candidacy_status.json",
                "rule": builder.CANDIDATE_UNIVERSE_RULE,
                "status_as_of": self.candidacy_status["status_as_of"],
                "count": len(self.candidacy_status["candidates"]),
            },
        )
        self.assertEqual(
            candidates,
            [
                {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_name": candidate["candidate_name"],
                }
                for candidate in self.candidacy_status["candidates"]
            ],
        )

    def test_poll_evidence_cannot_change_candidate_membership(self):
        first = builder.candidate_universe_from_candidacy_status(
            self.candidacy_status
        )
        changed_polls = [
            poll_event(
                candidates=[
                    ("Poll Only Person", 60),
                    ("Another Poll Only Person", 40),
                ]
            )
        ]
        builder.validated_first_round_events(changed_polls)
        second = builder.candidate_universe_from_candidacy_status(
            self.candidacy_status
        )
        self.assertEqual(first, second)
        self.assertNotIn(
            "Poll Only Person",
            {candidate["candidate_name"] for candidate in second[1]},
        )

    def test_invalid_registry_fails_closed(self):
        invalid = copy.deepcopy(self.candidacy_status)
        invalid["candidates"][0]["candidate_id"] = "Wrong-ID"
        with self.assertRaisesRegex(
            builder.CandidateSignalsError,
            "candidacy-status registry is invalid",
        ):
            builder.candidate_universe_from_candidacy_status(invalid)


class PollPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.polls, cls.news, cls.claims, cls.candidacy_status = builder.load_inputs(
            ROOT / "polls.json",
            ROOT / "news_wire.json",
            ROOT / "claims_under_scrutiny.json",
            ROOT / "candidate_candidacy_status.json",
        )
        cls.universe, cls.candidates = (
            builder.candidate_universe_from_candidacy_status(
                cls.candidacy_status
            )
        )

    def test_exact_package_key_and_sample_size_separation(self):
        first = poll_event(sample_size=1000, event_id="one")
        second = poll_event(sample_size=1001, event_id="two")
        packages = builder.build_poll_packages([first, second])
        self.assertEqual(len(packages), 2)
        self.assertEqual(
            packages[0]["package_key_values"],
            ["Alpha", "2026-07-09", "2026-07-10", 1000],
        )
        self.assertEqual(
            packages[0]["package_key"],
            '["Alpha","2026-07-09","2026-07-10",1000]',
        )

    def test_current_data_selects_documented_winning_package(self):
        packages = builder.build_poll_packages(self.polls)
        expected = min(
            packages,
            key=lambda package: (
                -date.fromisoformat(package["fieldwork_end"]).toordinal(),
                -package["selected_comparable_candidate_count"],
                builder.french_compatible_sort_key(package["pollster"]),
                package["original_package_index"],
            ),
        )
        selected = builder.select_featured_polling_package(self.polls)

        self.assertEqual(
            (
                selected["package_key"],
                selected["selected_event"]["event_id"],
                selected["selected_comparable_candidate_count"],
            ),
            (
                expected["package_key"],
                expected["selected_event"]["event_id"],
                expected["selected_comparable_candidate_count"],
            ),
        )
        self.assertTrue(
            all(
                builder._package_key(event)
                == builder._package_key(selected["selected_event"])
                for event in selected["events"]
            )
        )

    def test_newest_package_precedes_more_comparable_older_package(self):
        prior = poll_event(
            pollster="Alpha",
            fieldwork_start="2026-06-01",
            fieldwork_end="2026-06-02",
            scenario_key="alpha-scenario",
            event_id="alpha-prior",
        )
        older = poll_event(
            pollster="Alpha",
            fieldwork_start="2026-07-01",
            fieldwork_end="2026-07-02",
            scenario_key="alpha-scenario",
            event_id="alpha-older",
        )
        newer = poll_event(
            pollster="Zeta",
            fieldwork_start="2026-08-01",
            fieldwork_end="2026-08-02",
            scenario_key="zeta-scenario",
            event_id="zeta-newer",
        )

        polls = [prior, older, newer]
        packages = builder.build_poll_packages(polls)
        older_package = next(
            package
            for package in packages
            if package["selected_event"]["event_id"] == "alpha-older"
        )
        newer_package = next(
            package
            for package in packages
            if package["selected_event"]["event_id"] == "zeta-newer"
        )
        self.assertGreater(
            older_package["selected_comparable_candidate_count"],
            newer_package["selected_comparable_candidate_count"],
        )

        selected = builder.select_featured_polling_package(polls)

        self.assertEqual(selected["selected_event"]["event_id"], "zeta-newer")

    def test_official_source_precedes_reporting_source_downstream(self):
        event = poll_event(source_url="https://example.test/reporting")
        event["official_source_url"] = "https://example.test/original"
        package = builder.build_poll_packages([event])[0]

        public = builder._featured_package_public(package)

        self.assertEqual(
            public["source_urls"],
            ["https://example.test/original", "https://example.test/reporting"],
        )

    def test_ranges_use_only_featured_package_and_missing_is_not_zero(self):
        alpha_one = poll_event(
            pollster="Alpha",
            candidates=[("Candidate A", 60), ("Candidate B", 40)],
            event_id="alpha-one",
        )
        alpha_two = poll_event(
            pollster="Alpha",
            candidates=[("Candidate A", 55), ("Candidate B", 45)],
            event_id="alpha-two",
            scenario_key="scenario-two",
        )
        zeta = poll_event(
            pollster="Zeta",
            candidates=[("Candidate A", 10), ("Candidate C", 90)],
            event_id="zeta",
        )
        package = builder.select_featured_polling_package(
            [zeta, alpha_one, alpha_two]
        )
        projections = builder.project_candidate_polling(
            candidate_records("Candidate A", "Candidate B", "Candidate C"),
            package,
        )
        self.assertEqual(package["pollster"], "Alpha")
        self.assertEqual(
            projections["candidate-a"]["range_min"],
            55,
        )
        self.assertEqual(
            projections["candidate-a"]["range_max"],
            60,
        )
        self.assertEqual(
            projections["candidate-c"],
            {
                "evidence_state": "not_observed",
                "hypothesis_count": None,
                "range_min": None,
                "range_max": None,
                "selected_hypothesis_score": None,
                "selected_hypothesis_rank": None,
            },
        )

    def test_stable_input_order_is_final_package_tie_break(self):
        first = poll_event(sample_size=2000, event_id="first")
        second = poll_event(sample_size=1000, event_id="second")
        selected = builder.select_featured_polling_package([first, second])
        self.assertEqual(selected["sample_size"], 2000)

    def test_french_compatible_pollster_order(self):
        verian = poll_event(pollster="Verian", event_id="verian")
        elan = poll_event(pollster="Élan", event_id="elan")
        selected = builder.select_featured_polling_package([verian, elan])
        self.assertEqual(selected["pollster"], "Élan")

    def test_current_projection_cannot_include_verian_score(self):
        package = builder.select_featured_polling_package(self.polls)
        projection = builder.project_candidate_polling(
            self.candidates,
            package,
        )
        elabe_scores = [
            candidate["score"]
            for event in package["events"]
            for candidate in event["candidates"]
            if builder.normalized_candidate_key(candidate["name"])
            == "marine le pen"
        ]
        marine = projection["marine-le-pen"]
        self.assertEqual(marine["range_min"], min(elabe_scores))
        self.assertEqual(marine["range_max"], max(elabe_scores))
        self.assertEqual(marine["hypothesis_count"], len(elabe_scores))


class PollHistoryTests(unittest.TestCase):
    CANDIDATES = candidate_records(
        "Candidate A",
        "Candidate B",
        "Candidate C",
    )

    def test_history_reuses_packages_and_orders_oldest_first(self):
        older = poll_event(
            pollster="Alpha",
            fieldwork_start="2026-06-01",
            fieldwork_end="2026-06-02",
            event_id="older",
            candidates=[
                ("Candidate A", 60),
                ("Candidate B", 40),
            ],
        )
        newer = poll_event(
            pollster="Beta",
            fieldwork_start="2026-07-09",
            fieldwork_end="2026-07-10",
            event_id="newer",
            candidates=[
                ("Candidate A", 55),
                ("Candidate C", 45),
            ],
        )

        history = builder.project_candidate_poll_history(
            self.CANDIDATES,
            [newer, older],
        )

        candidate_a = history["candidate-a"]

        self.assertEqual(
            candidate_a["evidence_state"],
            "reported",
        )
        self.assertEqual(candidate_a["observation_count"], 2)
        self.assertEqual(candidate_a["period_start"], "2026-06-01")
        self.assertEqual(candidate_a["period_end"], "2026-07-10")

        self.assertEqual(
            [
                observation["pollster"]
                for observation in candidate_a["observations"]
            ],
            ["Alpha", "Beta"],
        )
        self.assertEqual(
            [
                observation["selected_score"]
                for observation in candidate_a["observations"]
            ],
            [60, 55],
        )

        candidate_b = history["candidate-b"]
        self.assertEqual(candidate_b["observation_count"], 1)
        self.assertEqual(
            candidate_b["observations"][0]["range_min"],
            40,
        )

    def test_history_preserves_range_when_selected_event_has_gap(self):
        selected = poll_event(
            pollster="Alpha",
            event_id="selected",
            scenario_key="selected-scenario",
            candidates=[
                ("Candidate A", 60),
                ("Candidate B", 40),
            ],
        )
        alternate = poll_event(
            pollster="Alpha",
            event_id="alternate",
            scenario_key="alternate-scenario",
            candidates=[
                ("Candidate A", 50),
                ("Candidate C", 50),
            ],
        )

        history = builder.project_candidate_poll_history(
            self.CANDIDATES,
            [selected, alternate],
        )

        candidate_c = history["candidate-c"]

        self.assertEqual(
            candidate_c["evidence_state"],
            "reported",
        )
        self.assertEqual(candidate_c["observation_count"], 1)

        observation = candidate_c["observations"][0]

        self.assertIsNone(observation["selected_score"])
        self.assertEqual(observation["range_min"], 50)
        self.assertEqual(observation["range_max"], 50)
        self.assertEqual(observation["hypothesis_count"], 1)

    def test_history_public_contract_validates(self):
        first = poll_event(
            pollster="Alpha",
            fieldwork_start="2026-06-01",
            fieldwork_end="2026-06-02",
            event_id="first-history",
            candidates=[
                ("Candidate A", 60),
                ("Candidate B", 40),
            ],
        )
        second = poll_event(
            pollster="Beta",
            fieldwork_start="2026-07-01",
            fieldwork_end="2026-07-02",
            event_id="second-history",
            candidates=[
                ("Candidate A", 55),
                ("Candidate C", 45),
            ],
        )

        history = builder.project_candidate_poll_history(
            self.CANDIDATES,
            [second, first],
        )

        for candidate_id, candidate_history in history.items():
            builder._validate_poll_history(
                candidate_history,
                f"fixture.{candidate_id}",
            )

    def test_history_validator_rejects_selected_score_outside_range(self):
        poll = poll_event(
            event_id="range-validation",
            candidates=[
                ("Candidate A", 60),
                ("Candidate B", 40),
            ],
        )
        history = builder.project_candidate_poll_history(
            self.CANDIDATES,
            [poll],
        )
        malformed = copy.deepcopy(history["candidate-a"])
        malformed["observations"][0]["selected_score"] = 99

        with self.assertRaisesRegex(
            builder.CandidateSignalsError,
            "falls outside package range",
        ):
            builder._validate_poll_history(
                malformed,
                "fixture.candidate-a",
            )

    def test_history_validator_rejects_non_chronological_observations(self):
        older = poll_event(
            pollster="Alpha",
            fieldwork_start="2026-06-01",
            fieldwork_end="2026-06-02",
            event_id="chronology-old",
            candidates=[
                ("Candidate A", 60),
                ("Candidate B", 40),
            ],
        )
        newer = poll_event(
            pollster="Beta",
            fieldwork_start="2026-07-01",
            fieldwork_end="2026-07-02",
            event_id="chronology-new",
            candidates=[
                ("Candidate A", 55),
                ("Candidate B", 45),
            ],
        )

        history = builder.project_candidate_poll_history(
            self.CANDIDATES,
            [newer, older],
        )
        malformed = copy.deepcopy(history["candidate-a"])
        malformed["observations"].reverse()

        with self.assertRaisesRegex(
            builder.CandidateSignalsError,
            "not chronological",
        ):
            builder._validate_poll_history(
                malformed,
                "fixture.candidate-a",
            )

    def test_history_does_not_infer_short_candidate_labels(self):
        short_label_poll = poll_event(
            event_id="short-label",
            candidates=[
                ("Attal", 60),
                ("Candidate B", 40),
            ],
        )

        candidates = candidate_records(
            "Gabriel Attal",
            "Candidate B",
        )

        history = builder.project_candidate_poll_history(
            candidates,
            [short_label_poll],
        )

        self.assertEqual(
            history["gabriel-attal"],
            {
                "evidence_state": "not_observed",
                "observation_count": 0,
                "period_start": None,
                "period_end": None,
                "observations": [],
            },
        )


class FeaturedPollBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.polls, cls.news, cls.claims, cls.candidacy_status = builder.load_inputs(
            ROOT / "polls.json",
            ROOT / "news_wire.json",
            ROOT / "claims_under_scrutiny.json",
            ROOT / "candidate_candidacy_status.json",
        )
        cls.package = builder.select_featured_polling_package(cls.polls)
        cls.selected_event = cls.package["selected_event"]
        cls.payload = builder.build_candidate_signals(
            cls.polls,
            cls.news,
            cls.claims,
            cls.candidacy_status,
        )

    def changed_payload(self):
        return copy.deepcopy(self.payload)

    def assert_board_rejected(self, change, pattern=None):
        payload = self.changed_payload()
        change(payload["featured_poll_board"])
        context = (
            self.assertRaisesRegex(builder.CandidateSignalsError, pattern)
            if pattern
            else self.assertRaises(builder.CandidateSignalsError)
        )
        with context:
            builder.validate_candidate_signals(payload)

    def test_current_board_matches_selected_package_and_event(self):
        board = self.payload["featured_poll_board"]
        featured_package = self.payload["featured_polling_package"]
        self.assertEqual(
            list(self.payload).index("featured_poll_board"),
            list(self.payload).index("featured_polling_package") + 1,
        )
        self.assertEqual(
            board["selection_basis"],
            "featured_package_selected_hypothesis",
        )
        self.assertEqual(
            featured_package,
            builder._featured_package_public(self.package),
        )
        hypothesis = self.selected_event.get("hypothesis")
        expected_label = (
            hypothesis.strip()
            if isinstance(hypothesis, str) and hypothesis.strip()
            else None
        )
        self.assertEqual(
            (
                board["pollster"],
                board["fieldwork_start"],
                board["fieldwork_end"],
                board["sample_size"],
                board["round"],
                board["scenario_key"],
                board["selected_event_id"],
                board["hypothesis_label"],
                board["package_hypothesis_count"],
                board["source_urls"],
            ),
            (
                self.package["pollster"],
                self.package["fieldwork_start"],
                self.package["fieldwork_end"],
                self.package["sample_size"],
                self.selected_event["round"],
                self.selected_event["scenario_key"],
                self.selected_event["event_id"],
                expected_label,
                len(self.package["events"]),
                featured_package["source_urls"],
            ),
        )

    def test_current_lineup_sort_limit_and_omission_are_dynamic(self):
        board = self.payload["featured_poll_board"]
        rows = board["candidates"]
        full_count = len(self.selected_event["candidates"])
        displayed_count = min(full_count, board["display_limit"])
        expected_rows = expected_featured_board_rows(
            self.selected_event,
            self.candidacy_status["candidates"],
            board["display_limit"],
        )

        self.assertEqual(board["full_candidate_count"], full_count)
        self.assertEqual(board["displayed_candidate_count"], displayed_count)
        self.assertEqual(
            board["omitted_candidate_count"],
            full_count - displayed_count,
        )
        self.assertEqual(rows, expected_rows)

    def test_synthetic_lineup_sort_limit_and_omission_are_exact(self):
        board = featured_poll_board_fixture()["board"]
        rows = board["candidates"]

        self.assertEqual(board["full_candidate_count"], 12)
        self.assertEqual(board["display_limit"], 10)
        self.assertEqual(board["displayed_candidate_count"], 10)
        self.assertEqual(board["omitted_candidate_count"], 2)
        self.assertEqual(
            [
                (
                    row["candidate_name"],
                    row["reported_score"],
                    row["source_position"],
                    row["display_position"],
                )
                for row in rows
            ],
            [
                ("Candidate B", 20, 2, 1),
                ("Candidate E", 15, 5, 2),
                ("Candidate F", 12, 6, 3),
                ("Candidate C", 10, 3, 4),
                ("Candidate D", 10, 4, 5),
                ("Candidate G", 9, 7, 6),
                ("Candidate H", 8, 8, 7),
                ("Candidate I", 6, 9, 8),
                ("Candidate J", 4, 10, 9),
                ("Candidate A", 3, 1, 10),
            ],
        )

    def test_every_board_row_comes_from_only_the_selected_event(self):
        board = self.payload["featured_poll_board"]
        selected_rows = expected_featured_board_rows(
            self.selected_event,
            self.candidacy_status["candidates"],
            len(self.selected_event["candidates"]),
        )
        selected = {
            row["candidate_id"]: (
                row["candidate_name"],
                row["source_position"],
                row["reported_score"],
            )
            for row in selected_rows
        }

        self.assertEqual(board["full_candidate_count"], len(selected))
        for row in board["candidates"]:
            self.assertIn(row["candidate_id"], selected)
            self.assertEqual(
                (
                    row["candidate_name"],
                    row["source_position"],
                    row["reported_score"],
                ),
                selected[row["candidate_id"]],
            )
        self.assertTrue(
            all(
                builder._package_key(event)
                == builder._package_key(self.selected_event)
                for event in self.package["events"]
            )
        )
        self.assertEqual(
            self.payload["featured_polling_package"][
                "selected_hypothesis_event_id"
            ],
            board["selected_event_id"],
        )

    def test_equal_scores_preserve_source_order(self):
        rows = featured_poll_board_fixture()["board"]["candidates"]
        names_at_ten = [
            row["candidate_name"]
            for row in rows
            if row["reported_score"] == 10
        ]

        self.assertEqual(names_at_ten, ["Candidate C", "Candidate D"])

    def test_candidate_id_is_only_the_final_defensive_tie_break(self):
        rows = [
            {"reported_score": 5, "source_position": 2, "candidate_id": "z"},
            {"reported_score": 5, "source_position": 1, "candidate_id": "z"},
            {"reported_score": 5, "source_position": 1, "candidate_id": "a"},
            {"reported_score": 6, "source_position": 9, "candidate_id": "x"},
        ]
        ordered = sorted(rows, key=builder._featured_poll_candidate_sort_key)
        self.assertEqual(
            [(row["reported_score"], row["source_position"], row["candidate_id"])
             for row in ordered],
            [(6, 9, "x"), (5, 1, "a"), (5, 1, "z"), (5, 2, "z")],
        )

    def test_candidate_universe_matches_complete_registry(self):
        expected = [
            (candidate["candidate_id"], candidate["candidate_name"])
            for candidate in self.candidacy_status["candidates"]
        ]
        actual = [
            (candidate["candidate_id"], candidate["candidate_name"])
            for candidate in self.payload["candidates"]
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(
            self.payload["candidate_universe"]["count"],
            len(expected),
        )

    def test_board_uses_no_range_or_cross_poll_synthetic_point(self):
        fixture = featured_poll_board_fixture()
        candidate_b = next(
            row
            for row in fixture["board"]["candidates"]
            if row["candidate_name"] == "Candidate B"
        )
        package_scores = [
            next(
                candidate["score"]
                for candidate in event["candidates"]
                if candidate["name"] == "Candidate B"
            )
            for event in fixture["package"]["events"]
        ]
        cross_poll_score = next(
            candidate["score"]
            for candidate in fixture["cross_poll_event"]["candidates"]
            if candidate["name"] == "Candidate B"
        )

        self.assertEqual(candidate_b["reported_score"], 20)
        self.assertEqual(package_scores, [20, 30])
        self.assertEqual(cross_poll_score, 40)
        self.assertIn(candidate_b["reported_score"], package_scores)
        self.assertNotEqual(candidate_b["reported_score"], cross_poll_score)
        self.assertEqual(
            candidate_b["reported_score"],
            next(
                candidate["score"]
                for candidate in fixture["selected_event"]["candidates"]
                if candidate["name"] == "Candidate B"
            ),
        )

    def test_build_does_not_mutate_any_source_object(self):
        polls = copy.deepcopy(self.polls)
        news = copy.deepcopy(self.news)
        claims = copy.deepcopy(self.claims)
        candidacy_status = copy.deepcopy(self.candidacy_status)
        originals = copy.deepcopy((polls, news, claims, candidacy_status))
        builder.build_candidate_signals(
            polls,
            news,
            claims,
            candidacy_status,
        )
        self.assertEqual(
            (polls, news, claims, candidacy_status),
            originals,
        )

    def test_board_is_required_and_top_level_keys_remain_exact(self):
        payload = self.changed_payload()
        del payload["featured_poll_board"]
        with self.assertRaisesRegex(builder.CandidateSignalsError, "unexpected fields"):
            builder.validate_candidate_signals(payload)
        payload = self.changed_payload()
        payload["unexpected"] = {}
        with self.assertRaisesRegex(builder.CandidateSignalsError, "unexpected fields"):
            builder.validate_candidate_signals(payload)

    def test_candidate_identity_failures_are_rejected(self):
        self.assert_board_rejected(
            lambda board: board["candidates"][0].__setitem__(
                "candidate_id", "unknown-candidate"
            ),
            "candidate_id is not in main candidates",
        )
        self.assert_board_rejected(
            lambda board: board["candidates"][1].__setitem__(
                "candidate_id", board["candidates"][0]["candidate_id"]
            ),
            "must be unique",
        )
        self.assert_board_rejected(
            lambda board: board["candidates"][0].__setitem__(
                "candidate_name", "Wrong Name"
            ),
            "not canonical",
        )

    def test_malformed_counts_and_display_limits_are_rejected(self):
        self.assert_board_rejected(
            lambda board: board.__setitem__("omitted_candidate_count", 2),
            "omitted count",
        )
        self.assert_board_rejected(
            lambda board: board.__setitem__("displayed_candidate_count", 9),
            "displayed count",
        )
        self.assert_board_rejected(
            lambda board: board.__setitem__("display_limit", 0),
            "positive integer",
        )

    def test_invalid_positions_and_ordering_are_rejected(self):
        self.assert_board_rejected(
            lambda board: board["candidates"][1].__setitem__(
                "display_position", 3
            ),
            "display positions",
        )
        self.assert_board_rejected(
            lambda board: board["candidates"][1].__setitem__(
                "source_position", board["candidates"][0]["source_position"]
            ),
            "source positions",
        )

        def descending_change(board):
            board["candidates"][0], board["candidates"][1] = (
                board["candidates"][1],
                board["candidates"][0],
            )
            for position, row in enumerate(board["candidates"], start=1):
                row["display_position"] = position

        self.assert_board_rejected(descending_change, "correctly ordered")

        def equal_score_change(board):
            board["candidates"][3], board["candidates"][4] = (
                board["candidates"][4],
                board["candidates"][3],
            )
            for position, row in enumerate(board["candidates"], start=1):
                row["display_position"] = position

        self.assert_board_rejected(equal_score_change, "correctly ordered")

    def test_invalid_urls_dates_and_selected_metadata_are_rejected(self):
        cases = (
            (
                "invalid URL",
                lambda board: board.__setitem__(
                    "source_urls",
                    ["relative/path"],
                ),
                "source_urls",
            ),
            (
                "duplicate URL",
                lambda board: board["source_urls"].append(
                    board["source_urls"][0]
                ),
                "source_urls",
            ),
            (
                "invalid calendar date",
                lambda board: board.__setitem__(
                    "fieldwork_start",
                    "2026-02-30",
                ),
                "ISO calendar date",
            ),
            (
                "reversed dates",
                lambda board: board.__setitem__(
                    "fieldwork_start",
                    (
                        date.fromisoformat(board["fieldwork_end"])
                        + timedelta(days=1)
                    ).isoformat(),
                ),
                "dates are reversed",
            ),
            (
                "empty scenario",
                lambda board: board.__setitem__("scenario_key", ""),
                "non-empty string",
            ),
            (
                "selected event mismatch",
                lambda board: board.__setitem__(
                    "selected_event_id",
                    "other",
                ),
                "does not match featured polling package",
            ),
        )
        for name, change, pattern in cases:
            with self.subTest(case=name):
                self.assert_board_rejected(change, pattern)

class VisibilityTests(unittest.TestCase):
    def test_campaign_and_general_projections_stay_separate(self):
        candidates = candidate_records("Candidate A", "Candidate B")
        news = news_fixture()
        visibility, campaign, general = builder.project_visibility(
            candidates,
            news,
        )
        self.assertEqual(visibility["current_period"]["record_count"], 1)
        self.assertEqual(
            visibility["general_current_period"]["record_count"],
            1,
        )
        self.assertEqual(campaign["candidate-a"]["scope_counts"]["general"], 0)
        self.assertNotIn("scope_counts", general["candidate-a"])
        self.assertEqual(
            campaign["candidate-b"]["evidence_state"],
            "not_observed",
        )
        self.assertIsNone(campaign["candidate-b"]["record_count"])
        self.assertEqual(
            general["candidate-b"]["evidence_state"],
            "not_observed",
        )

    def test_summary_cluster_and_concentration_survive_without_arrays(self):
        candidates = candidate_records("Candidate A", "Candidate B")
        visibility, campaign, general = builder.project_visibility(
            candidates,
            news_fixture(),
        )
        self.assertEqual(campaign["candidate-a"]["story_cluster_count"], 1)
        self.assertEqual(
            campaign["candidate-a"]["concentration"],
            concentration(),
        )
        self.assertEqual(general["candidate-a"]["story_cluster_count"], 1)
        serialized = json.dumps(
            {
                "visibility": visibility,
                "campaign": campaign,
                "general": general,
            }
        )
        self.assertNotIn("story_clusters", serialized)
        self.assertNotIn("publisher_names", serialized)

    def test_comparison_quality_survives_without_candidate_delta(self):
        candidates = candidate_records("Candidate A", "Candidate B")
        news = news_fixture()
        visibility, campaign, _general = builder.project_visibility(
            candidates,
            news,
        )
        self.assertEqual(
            visibility["comparison_quality"],
            news["candidate_visibility"]["comparison_quality"],
        )
        self.assertNotIn("delta", json.dumps(campaign).lower())

    def test_invalid_primary_general_partition_fails(self):
        news = news_fixture()
        metric = news["candidate_visibility"]["current_period"][
            "candidate_metrics"
        ][0]
        metric["scope_counts"] = {
            "election": 0,
            "campaign": 0,
            "general": 1,
        }
        with self.assertRaisesRegex(
            builder.CandidateSignalsError,
            "general records",
        ):
            builder.project_visibility(
                candidate_records("Candidate A", "Candidate B"),
                news,
            )


class ScrutinyTests(unittest.TestCase):
    def setUp(self):
        self.candidates = candidate_records("Candidate A", "Candidate B")

    def test_by_about_boundaries_archive_and_missing_candidate(self):
        claims = claims_fixture(
            generated_at="2026-07-20T12:00:00Z",
            reviews=[
                review(
                    "start",
                    "2026-07-07",
                    [association("Candidate A", "by")],
                ),
                review(
                    "before",
                    "2026-07-06",
                    [association("Candidate A", "about")],
                ),
                review(
                    "end",
                    "2026-07-20",
                    [association("Candidate A", "about")],
                ),
            ],
        )
        window, projection, evidence = builder.project_scrutiny(
            self.candidates,
            claims,
        )
        self.assertEqual(window["latest_start_date"], "2026-07-07")
        self.assertEqual(window["latest_end_date"], "2026-07-20")
        latest = projection["candidate-a"]["latest_14_days"]
        archive = projection["candidate-a"]["archive"]
        self.assertEqual(
            (latest["review_count"], latest["by_count"], latest["about_count"]),
            (2, 1, 1),
        )
        self.assertEqual(
            (archive["review_count"], archive["by_count"], archive["about_count"]),
            (3, 1, 2),
        )
        self.assertEqual(latest["newest_review_date"], "2026-07-20")
        self.assertEqual(evidence, "2026-07-20")
        self.assertEqual(
            projection["candidate-b"]["latest_14_days"],
            {
                "review_count": 0,
                "by_count": 0,
                "about_count": 0,
                "newest_review_date": None,
                "newest_review_url": None,
            },
        )

    def test_same_day_generated_time_does_not_change_projection(self):
        first = claims_fixture(generated_at="2026-07-20T00:01:00Z")
        second = claims_fixture(generated_at="2026-07-20T23:59:00Z")
        self.assertEqual(
            builder.project_scrutiny(self.candidates, first),
            builder.project_scrutiny(self.candidates, second),
        )

    def test_successive_generated_dates_advance_latest_window(self):
        reviews = [
            review(
                "same-review",
                "2026-07-15",
                [association("Candidate A", "by")],
            )
        ]
        first = claims_fixture(
            generated_at="2026-07-20T23:59:00Z",
            reviews=copy.deepcopy(reviews),
        )
        second = claims_fixture(
            generated_at="2026-07-21T00:01:00Z",
            reviews=copy.deepcopy(reviews),
        )

        first_window, _first_projection, _first_evidence = builder.project_scrutiny(
            self.candidates,
            first,
        )
        second_window, _second_projection, _second_evidence = builder.project_scrutiny(
            self.candidates,
            second,
        )

        self.assertEqual(first_window["latest_start_date"], "2026-07-07")
        self.assertEqual(first_window["latest_end_date"], "2026-07-20")
        self.assertEqual(second_window["latest_start_date"], "2026-07-08")
        self.assertEqual(second_window["latest_end_date"], "2026-07-21")

    def test_future_review_date_fails(self):
        claims = claims_fixture(
            generated_at="2026-07-20T12:00:00Z",
            reviews=[
                review(
                    "future",
                    "2026-07-21",
                    [association("Candidate A", "by")],
                )
            ],
        )
        with self.assertRaisesRegex(
            builder.CandidateSignalsError,
            "future",
        ):
            builder.project_scrutiny(self.candidates, claims)

    def test_registry_stable_id_need_not_be_slug_of_current_name(self):
        candidates = [
            {
                "candidate_id": "alice-ancienne",
                "candidate_name": "Alice Nouvelle",
            }
        ]
        claims = claims_fixture(
            reviews=[
                review(
                    "renamed",
                    "2026-07-20",
                    [
                        {
                            "candidate_id": "alice-ancienne",
                            "candidate_name": "Alice Nouvelle",
                            "relationship": "by",
                        }
                    ],
                )
            ]
        )
        _window, projection, _evidence = builder.project_scrutiny(
            candidates,
            claims,
        )
        self.assertEqual(
            projection["alice-ancienne"]["archive"]["review_count"],
            1,
        )

    def test_zero_claims_does_not_change_candidate_membership(self):
        _window, projection, evidence = builder.project_scrutiny(
            self.candidates,
            claims_fixture(reviews=[]),
        )
        self.assertEqual(set(projection), {"candidate-a", "candidate-b"})
        self.assertEqual(projection["candidate-a"]["archive"]["review_count"], 0)
        self.assertIsNone(evidence)

    def test_invalid_relationship_fails(self):
        claims = claims_fixture(
            reviews=[
                review(
                    "invalid",
                    "2026-07-20",
                    [association("Candidate A", "endorses")],
                )
            ]
        )
        with self.assertRaisesRegex(
            builder.CandidateSignalsError,
            "by or about",
        ):
            builder.project_scrutiny(self.candidates, claims)


class LatestDevelopmentTests(unittest.TestCase):
    def test_newest_campaign_record_wins_and_newer_general_is_ignored(self):
        items = [
            watch_item(
                "general-new",
                "2026-07-21T10:00:00Z",
                "general",
            ),
            watch_item(
                "campaign-old",
                "2026-07-20T10:00:00Z",
                "campaign",
            ),
            watch_item(
                "election-older",
                "2026-07-19T10:00:00Z",
                "election",
            ),
        ]
        selected = builder.select_latest_development(
            "Candidate A",
            items,
        )
        self.assertEqual(selected["id"], "campaign-old")
        self.assertEqual(selected["coverage_scope"], "campaign")

    def test_record_id_is_deterministic_timestamp_tie_break(self):
        items = [
            watch_item("z-record", "2026-07-20T10:00:00Z", "campaign"),
            watch_item("a-record", "2026-07-20T10:00:00Z", "campaign"),
        ]
        selected = builder.select_latest_development(
            "Candidate A",
            items,
        )
        self.assertEqual(selected["id"], "a-record")

    def test_missing_url_record_is_rejected_from_selection(self):
        items = [
            watch_item(
                "missing-source",
                "2026-07-21T10:00:00Z",
                "campaign",
                url="",
            ),
            watch_item(
                "source-linked",
                "2026-07-20T10:00:00Z",
                "election",
            ),
        ]
        selected = builder.select_latest_development(
            "Candidate A",
            items,
        )
        self.assertEqual(selected["id"], "source-linked")

    def test_headline_candidate_remains_eligible(self):
        selected = builder.select_latest_development(
            "Candidate A",
            [
                watch_item(
                    "headline-subject",
                    "2026-07-20T10:00:00Z",
                    "election",
                )
            ],
        )

        self.assertEqual(selected["evidence_state"], "reported")
        self.assertEqual(selected["id"], "headline-subject")

    def test_summary_only_contextual_candidate_is_rejected(self):
        contextual = watch_item(
            "candidate-b-subject",
            "2026-07-21T10:00:00Z",
            "election",
            candidate_matches=[
                candidate_match("Candidate B", "headline"),
                candidate_match("Candidate A", "summary"),
            ],
        )

        candidate_a = builder.select_latest_development(
            "Candidate A",
            [contextual],
        )
        candidate_b = builder.select_latest_development(
            "Candidate B",
            [contextual],
        )

        self.assertEqual(candidate_a["evidence_state"], "none")
        self.assertIsNone(candidate_a["id"])
        self.assertEqual(candidate_b["evidence_state"], "reported")
        self.assertEqual(candidate_b["id"], "candidate-b-subject")

    def test_older_headline_record_beats_newer_summary_only_record(self):
        items = [
            watch_item(
                "candidate-a-direct",
                "2026-07-20T10:00:00Z",
                "campaign",
            ),
            watch_item(
                "candidate-b-newer",
                "2026-07-21T10:00:00Z",
                "election",
                candidate_matches=[
                    candidate_match("Candidate B", "headline"),
                    candidate_match("Candidate A", "summary"),
                ],
            ),
        ]

        selected = builder.select_latest_development(
            "Candidate A",
            items,
        )

        self.assertEqual(selected["evidence_state"], "reported")
        self.assertEqual(selected["id"], "candidate-a-direct")

    def test_only_summary_provenance_produces_no_direct_subject_evidence(self):
        items = [
            watch_item(
                "context-one",
                "2026-07-20T10:00:00Z",
                "campaign",
                candidate_matches=[
                    candidate_match("Candidate B", "headline"),
                    candidate_match("Candidate A", "summary"),
                ],
            ),
            watch_item(
                "context-two",
                "2026-07-21T10:00:00Z",
                "election",
                candidate_matches=[
                    candidate_match("Candidate B", "headline"),
                    candidate_match("Candidate A", "summary"),
                ],
            ),
        ]

        selected = builder.select_latest_development(
            "Candidate A",
            items,
        )

        self.assertEqual(selected["evidence_state"], "none")
        self.assertIsNone(selected["id"])
        self.assertIsNone(selected["published_at"])
        self.assertIsNone(selected["url"])

    def test_multi_candidate_headline_keeps_both_candidates_eligible(self):
        shared = watch_item(
            "shared-headline",
            "2026-07-20T10:00:00Z",
            "election",
            candidate_matches=[
                candidate_match("Candidate A", "headline"),
                candidate_match("Candidate B", "headline"),
            ],
        )

        candidate_a = builder.select_latest_development(
            "Candidate A",
            [shared],
        )
        candidate_b = builder.select_latest_development(
            "Candidate B",
            [shared],
        )

        self.assertEqual(candidate_a["id"], "shared-headline")
        self.assertEqual(candidate_b["id"], "shared-headline")

    def test_project_latest_developments_uses_same_subject_rule(self):
        candidates = candidate_records(
            "Candidate A",
            "Candidate B",
        )
        items = [
            watch_item(
                "candidate-a-direct",
                "2026-07-20T10:00:00Z",
                "campaign",
            ),
            watch_item(
                "candidate-b-newer",
                "2026-07-22T10:00:00Z",
                "election",
                candidate_matches=[
                    candidate_match("Candidate B", "headline"),
                    candidate_match("Candidate A", "summary"),
                ],
            ),
        ]

        developments, evidence_date = (
            builder.project_latest_developments(
                candidates,
                items,
            )
        )

        self.assertEqual(
            developments["candidate-a"]["id"],
            "candidate-a-direct",
        )
        self.assertEqual(
            developments["candidate-b"]["id"],
            "candidate-b-newer",
        )
        self.assertEqual(evidence_date, "2026-07-22")

    def test_malformed_candidate_match_provenance_fails_closed(self):
        malformed = watch_item(
            "malformed-provenance",
            "2026-07-20T10:00:00Z",
            "election",
        )
        malformed["candidate_matches"][0]["locations"] = ["body"]

        with self.assertRaisesRegex(
            builder.CandidateSignalsError,
            r"candidate_matches\[0\]\.locations is invalid",
        ):
            builder.select_latest_development(
                "Candidate A",
                [malformed],
            )


class PresidentialFieldContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (
            cls.polls,
            cls.news,
            cls.claims,
            cls.registry,
        ) = builder.load_inputs(
            ROOT / "polls.json",
            ROOT / "news_wire.json",
            ROOT / "claims_under_scrutiny.json",
            ROOT / "candidate_candidacy_status.json",
        )
        cls.payload = builder.build_candidate_signals(
            cls.polls,
            cls.news,
            cls.claims,
            cls.registry,
        )

    def test_schema_keys_complete_universe_and_order_are_exact(self):
        self.assertEqual(self.payload["schema_version"], "1.5")
        self.assertEqual(
            list(self.payload),
            [
                "schema_version",
                "candidate_universe",
                "presidential_field",
                "active_monitoring_field",
                "active_field_visibility",
                "featured_polling_package",
                "featured_poll_board",
                "visibility",
                "scrutiny_window",
                "evidence_dates",
                "candidates",
            ],
        )
        self.assertIn("active_field_visibility", self.payload)
        self.assertEqual(
            len(self.payload["candidates"]),
            len(self.registry["candidates"]),
        )
        order = [
            (candidate["candidate_name"].casefold(), candidate["candidate_id"])
            for candidate in self.payload["candidates"]
        ]
        self.assertEqual(order, sorted(order))
        self.assertEqual(
            set(self.payload["candidates"][0]),
            {
                "candidate_id",
                "candidate_name",
                "candidacy",
                "polling",
                "poll_history",
                "campaign_attention",
                "general_visibility",
                "scrutiny",
                "latest_development",
                "agenda_profile",
            },
        )

    def test_active_field_visibility_contract_and_fixture_values(self):
        active = self.payload["active_field_visibility"]
        expected = builder.derive_active_field_visibility(
            self.news,
            self.payload["active_monitoring_field"],
            self.registry,
        )
        self.assertEqual(active, expected)
        self.assertEqual(
            set(active),
            {"method", "denominator_scope", "status_as_of", "primary", "general"},
        )
        self.assertEqual(
            active["method"],
            "share_of_active_candidate_linked_records",
        )
        self.assertEqual(
            active["denominator_scope"],
            "records_linked_to_at_least_one_active_monitoring_candidate",
        )
        self.assertEqual(
            active["status_as_of"],
            self.payload["presidential_field"]["status_as_of"],
        )
        field = self.payload["active_monitoring_field"]
        active_ids = set(field["main"] + field["secondary"])
        hidden = set(self.payload["presidential_field"]["hidden"])
        row_keys = {
            "candidate_id", "candidate_name", "status", "display_tier",
            "current_record_count", "current_share", "prior_record_count",
            "prior_share", "share_change",
        }
        for scope_name in ("primary", "general"):
            scope = active[scope_name]
            self.assertEqual(
                set(scope),
                {"current_period", "prior_period", "comparison_quality", "main", "secondary"},
            )
            current_count = scope["current_period"]["record_count"]
            prior_count = scope["prior_period"]["record_count"]
            quality = scope["comparison_quality"]
            self.assertEqual(quality["current_record_count"], current_count)
            self.assertEqual(quality["prior_record_count"], prior_count)
            self.assertEqual(
                quality["current_publisher_count"],
                scope["current_period"]["publisher_count"],
            )
            self.assertEqual(
                quality["prior_publisher_count"],
                scope["prior_period"]["publisher_count"],
            )
            self.assertEqual(len(scope["main"]), field["counts"]["main"])
            self.assertEqual(len(scope["secondary"]), field["counts"]["secondary"])
            rows = scope["main"] + scope["secondary"]
            self.assertEqual({row["candidate_id"] for row in rows}, active_ids)
            self.assertFalse(hidden & {row["candidate_id"] for row in rows})
            for row in rows:
                self.assertEqual(set(row), row_keys)
                expected_current = (
                    builder._round_visibility_ratio(
                        row["current_record_count"] / current_count
                    )
                    if current_count
                    else None
                )
                expected_prior = (
                    builder._round_visibility_ratio(
                        row["prior_record_count"] / prior_count
                    )
                    if prior_count
                    else None
                )
                self.assertEqual(row["current_share"], expected_current)
                self.assertEqual(row["prior_share"], expected_prior)
                if (
                    quality["status"] == "comparable"
                    and expected_current is not None
                    and expected_prior is not None
                ):
                    self.assertEqual(
                        row["share_change"],
                        builder._round_visibility_ratio(
                            expected_current - expected_prior
                        ),
                    )
                else:
                    self.assertIsNone(row["share_change"])
            for tier in ("main", "secondary"):
                self.assertEqual(
                    scope[tier],
                    sorted(scope[tier], key=builder._active_row_sort_key),
                )
        compact_top_five = [
            row["candidate_id"]
            for row in sorted(
                active["primary"]["main"] + active["primary"]["secondary"],
                key=builder._active_row_sort_key,
            )[:5]
        ]
        self.assertEqual(len(compact_top_five), min(5, field["counts"]["active"]))
        self.assertEqual(len(compact_top_five), len(set(compact_top_five)))

    def test_active_union_reconciliation_uses_published_record_associations(self):
        before = copy.deepcopy(self.news)
        field = self.payload["active_monitoring_field"]
        names_by_id = {
            candidate["candidate_id"]: candidate["candidate_name"]
            for candidate in self.payload["candidates"]
        }
        active_names = {
            names_by_id[identifier]
            for tier in ("main", "secondary")
            for identifier in field[tier]
        }
        hidden_names = {
            names_by_id[identifier]
            for identifier in self.payload["presidential_field"]["hidden"]
        }
        records = self.news["candidate_watch"]
        self.assertEqual(
            len(records),
            len({record["id"] for record in records}),
        )
        self.assertTrue(all(
            record["candidates"]
            == [match["candidate"] for match in record["candidate_matches"]]
            for record in records
        ))
        visibility = self.news["candidate_visibility"]
        active = self.payload["active_field_visibility"]
        specifications = {
            "primary_current": (
                visibility["current_period"],
                {"election", "campaign"},
                active["primary"]["current_period"],
            ),
            "primary_prior": (
                visibility["prior_period"],
                {"election", "campaign"},
                active["primary"]["prior_period"],
            ),
            "general_current": (
                visibility["general_current_period"],
                {"general"},
                active["general"]["current_period"],
            ),
            "general_prior": (
                visibility["general_prior_period"],
                {"general"},
                active["general"]["prior_period"],
            ),
        }
        for period, scopes, projection in specifications.values():
            qualifying = [
                record for record in records
                if period["start_date"] <= record["published_at"][:10] <= period["end_date"]
                and record["coverage_scope"] in scopes
            ]
            active_records = [
                record for record in qualifying
                if active_names & set(record["candidates"])
            ]
            hidden_only = [
                record for record in qualifying
                if hidden_names & set(record["candidates"])
                and not active_names & set(record["candidates"])
            ]
            mixed = [
                record for record in qualifying
                if hidden_names & set(record["candidates"])
                and active_names & set(record["candidates"])
            ]
            active_record_ids = {record["id"] for record in active_records}
            hidden_only_ids = {record["id"] for record in hidden_only}
            mixed_ids = {record["id"] for record in mixed}
            active_publishers = {record["publisher"] for record in active_records}
            self.assertEqual(len(qualifying), period["record_count"])
            self.assertEqual(len(active_record_ids), projection["record_count"])
            self.assertEqual(len(active_publishers), projection["publisher_count"])
            self.assertTrue(hidden_only_ids.isdisjoint(active_record_ids))
            self.assertTrue(mixed_ids.issubset(active_record_ids))
        builder.derive_active_field_visibility(self.news, field, self.registry)
        self.assertEqual(self.news, before)

    def test_zero_denominator_uses_missing_shares_and_null_changes(self):
        news = copy.deepcopy(self.news)
        news["candidate_watch"] = []
        for period_name in (
            "current_period", "prior_period",
            "general_current_period", "general_prior_period",
        ):
            period = news["candidate_visibility"][period_name]
            period["record_count"] = 0
            period["publisher_count"] = 0
            period["publisher_names"] = []
            period["candidate_metrics"] = []
        active = builder.derive_active_field_visibility(
            news,
            self.payload["active_monitoring_field"],
            self.registry,
        )
        for scope_name in ("primary", "general"):
            scope = active[scope_name]
            self.assertEqual(scope["current_period"]["record_count"], 0)
            self.assertEqual(scope["comparison_quality"]["status"], "not_comparable")
            for row in scope["main"] + scope["secondary"]:
                self.assertEqual(row["current_record_count"], 0)
                self.assertIsNone(row["current_share"])
                self.assertIsNone(row["prior_share"])
                self.assertIsNone(row["share_change"])

    def test_active_visibility_validator_rejects_fabricated_primary_change(self):
        malformed = copy.deepcopy(self.payload)
        malformed["active_field_visibility"]["primary"]["main"][0]["share_change"] = 0
        with self.assertRaises(builder.CandidateSignalsError):
            builder.validate_candidate_signals(malformed)

    def test_candidacy_and_presidential_field_are_exact_registry_projections(self):
        registry_by_id = {
            candidate["candidate_id"]: candidate
            for candidate in self.registry["candidates"]
        }
        for candidate in self.payload["candidates"]:
            source = registry_by_id[candidate["candidate_id"]]
            expected = {
                key: source[key]
                for key in (
                    "status",
                    "display_tier",
                    "status_as_of",
                    "source_date",
                    "source_url",
                    "source_title",
                    "source_publisher",
                    "status_note",
                )
            }
            expected["upstream_presence"] = source.get(
                "upstream_presence",
                "present",
            )
            expected["active_field_eligible"] = candidate["candidate_id"] in set(
                self.payload["active_monitoring_field"]["main"]
                + self.payload["active_monitoring_field"]["secondary"]
            )
            self.assertEqual(candidate["candidacy"], expected)
        field = self.payload["presidential_field"]
        self.assertEqual(
            set(field),
            {"status_as_of", "main", "secondary", "hidden", "counts"},
        )
        self.assertEqual(
            field,
            builder.project_display_tiers(self.registry),
        )
        self.assertEqual(
            self.payload["active_monitoring_field"],
            builder.project_active_monitoring_field(self.registry),
        )
        all_ids = field["main"] + field["secondary"] + field["hidden"]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(
            set(all_ids),
            {candidate["candidate_id"] for candidate in self.payload["candidates"]},
        )

    def test_hidden_and_conditional_poll_figures_are_not_filtered(self):
        rows = self.payload["featured_poll_board"]["candidates"]
        self.assertIn("eric-zemmour", {row["candidate_id"] for row in rows})
        payload_ids = {candidate["candidate_id"] for candidate in self.payload["candidates"]}
        self.assertIn("sarah-knafo", payload_ids)
        self.assertIn("sebastien-lecornu", payload_ids)

    def test_malformed_registry_stops_build(self):
        mutations = []
        unknown = copy.deepcopy(self.registry)
        unknown["candidates"][0]["candidate_id"] = "unknown-candidate"
        mutations.append(unknown)
        wrong_name = copy.deepcopy(self.registry)
        wrong_name["candidates"][0]["candidate_name"] = "Wrong Name"
        mutations.append(wrong_name)
        for registry in mutations:
            with self.subTest(registry=registry):
                with self.assertRaises(builder.CandidateSignalsError):
                    builder.build_candidate_signals(
                        self.polls,
                        self.news,
                        self.claims,
                        registry,
                    )

    def test_registry_path_failures_preserve_last_good_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "candidate_signals.json"
            output.write_text("last-good\n", encoding="utf-8")
            missing = root / "missing.json"
            with self.assertRaisesRegex(builder.CandidateSignalsError, "missing"):
                builder.build_from_paths(
                    ROOT / "polls.json",
                    ROOT / "news_wire.json",
                    ROOT / "claims_under_scrutiny.json",
                    missing,
                    output,
                )
            malformed = root / "malformed.json"
            malformed.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(builder.CandidateSignalsError, "malformed"):
                builder.build_from_paths(
                    ROOT / "polls.json",
                    ROOT / "news_wire.json",
                    ROOT / "claims_under_scrutiny.json",
                    malformed,
                    output,
                )
            self.assertEqual(output.read_text(encoding="utf-8"), "last-good\n")


class DeterminismAndSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (
            cls.current_polls,
            cls.current_news,
            cls.current_claims,
            cls.current_candidacy_status,
        ) = builder.load_inputs(
            ROOT / "polls.json",
            ROOT / "news_wire.json",
            ROOT / "claims_under_scrutiny.json",
            ROOT / "candidate_candidacy_status.json",
        )

    def fixture_payload(self, *, news=None, claims=None):
        return builder.build_candidate_signals(
            copy.deepcopy(self.current_polls),
            copy.deepcopy(news or self.current_news),
            copy.deepcopy(claims or self.current_claims),
            copy.deepcopy(self.current_candidacy_status),
        )

    def test_identical_builds_are_byte_identical(self):
        first = builder.serialize_candidate_signals(self.fixture_payload())
        second = builder.serialize_candidate_signals(self.fixture_payload())
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))

    def test_same_day_raw_generated_times_do_not_change_output(self):
        first_news = copy.deepcopy(self.current_news)
        first_claims = copy.deepcopy(self.current_claims)
        second_news = copy.deepcopy(self.current_news)
        second_claims = copy.deepcopy(self.current_claims)
        source_day = self.current_claims["generated_at"][:10]
        first_news["generated_at"] = f"{source_day}T00:01:00Z"
        first_claims["generated_at"] = f"{source_day}T00:01:00Z"
        second_news["generated_at"] = f"{source_day}T23:59:00Z"
        second_claims["generated_at"] = f"{source_day}T23:59:00Z"
        first = self.fixture_payload(news=first_news, claims=first_claims)
        second = self.fixture_payload(news=second_news, claims=second_claims)
        self.assertEqual(
            builder.serialize_candidate_signals(first),
            builder.serialize_candidate_signals(second),
        )

    def test_candidate_order_is_name_then_id(self):
        payload = self.fixture_payload()
        order = [
            (candidate["candidate_name"].casefold(), candidate["candidate_id"])
            for candidate in payload["candidates"]
        ]
        self.assertEqual(order, sorted(order))

    def test_forbidden_interpretive_field_audit(self):
        payload = self.fixture_payload()
        payload["momentum"] = 1
        with self.assertRaisesRegex(
            builder.CandidateSignalsError,
            "forbidden interpretive field",
        ):
            builder.validate_candidate_signals(payload)

    def test_malformed_json_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            malformed = root / "malformed.json"
            malformed.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(
                builder.CandidateSignalsError,
                "malformed JSON",
            ):
                builder.load_json(malformed)

    def test_failed_build_does_not_replace_last_good_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            polls_path = root / "polls.json"
            news_path = root / "news.json"
            claims_path = root / "claims.json"
            output_path = root / "candidate_signals.json"
            polls_path.write_text("{broken", encoding="utf-8")
            news_path.write_text(
                json.dumps(news_fixture()),
                encoding="utf-8",
            )
            claims_path.write_text(
                json.dumps(claims_fixture()),
                encoding="utf-8",
            )
            output_path.write_text("last-good\n", encoding="utf-8")
            with self.assertRaises(builder.CandidateSignalsError):
                builder.build_from_paths(
                    polls_path,
                    news_path,
                    claims_path,
                    ROOT / "candidate_candidacy_status.json",
                    output_path,
                )
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "last-good\n",
            )

    def test_current_sources_build_a_valid_dynamic_payload(self):
        payload = self.fixture_payload()
        builder.validate_candidate_signals(
            payload,
            polls=self.current_polls,
            news=self.current_news,
            claims=self.current_claims,
            candidacy_status=self.current_candidacy_status,
        )
        self.assertEqual(
            payload["candidate_universe"]["count"],
            len(self.current_candidacy_status["candidates"]),
        )
        selected_package = builder.select_featured_polling_package(
            self.current_polls
        )
        self.assertEqual(
            payload["featured_polling_package"],
            builder._featured_package_public(selected_package),
        )
        self.assertEqual(
            payload["featured_poll_board"]["selected_event_id"],
            selected_package["selected_event"]["event_id"],
        )
        registry_ids = {
            candidate["candidate_id"]
            for candidate in self.current_candidacy_status["candidates"]
        }
        self.assertTrue(
            all(
                row["candidate_id"] in registry_ids
                for row in payload["featured_poll_board"]["candidates"]
            )
        )
        serialized = json.dumps(payload)
        self.assertNotIn('"story_clusters"', serialized)
        self.assertNotIn('"publisher_names"', serialized)
        self.assertNotIn('"delta"', serialized)


class AgendaProfileContractTests(unittest.TestCase):
    CANDIDATES = [
        {
            "candidate_id": "alice-observee",
            "candidate_name": "Alice Observée",
        },
        {
            "candidate_id": "benoit-non-teste",
            "candidate_name": "Benoît Non Testé",
        },
    ]

    def news_payload(self, policy_counts=None, relevant_news=None):
        policy_counts = policy_counts or {}
        relevant_news = relevant_news or []

        return {
            "policy_agenda": {
                "window_days": 30,
                "evolution": {
                    "period_start": "2026-07-01",
                    "period_end": "2026-07-30",
                },
                "topics": [
                    {
                        "id": definition["id"],
                        "candidate_counts": (
                            [{
                                "candidate": "Alice Observée",
                                "item_count": policy_counts[definition["id"]],
                            }]
                            if policy_counts.get(definition["id"], 0) > 0
                            else []
                        ),
                    }
                    for definition in builder.POLICY_AGENDA_TOPICS
                ],
            },
            "relevant_news": relevant_news,
        }

    def campaign_record(
        self,
        headline,
        published_at,
        candidates=None,
    ):
        return {
            "headline": headline,
            "published_at": published_at,
            "candidates": (
                ["Alice Observée"]
                if candidates is None
                else candidates
            ),
            "explicit_election": True,
        }

    def test_three_nonzero_policy_topics_select_policy_wholesale(self):
        policy_ids = [
            definition["id"]
            for definition in builder.POLICY_AGENDA_TOPICS
        ]
        news = self.news_payload(
            policy_counts={
                policy_ids[0]: 2,
                policy_ids[1]: 1,
                policy_ids[2]: 1,
            },
            relevant_news=[
                self.campaign_record(
                    "Alice Observée annonce sa candidature "
                    "à l'élection présidentielle",
                    "2026-07-15T12:00:00Z",
                ),
            ],
        )

        profiles = builder.project_agenda_profiles(
            self.CANDIDATES,
            news,
        )
        profile = profiles["alice-observee"]

        self.assertEqual(profile["profile_mode"], "policy")
        self.assertEqual(profile["window_days"], 30)
        self.assertEqual(profile["period_start"], "2026-07-01")
        self.assertEqual(profile["period_end"], "2026-07-30")
        self.assertEqual(profile["association_count"], 4)
        self.assertEqual(
            [topic["id"] for topic in profile["topics"]],
            policy_ids,
        )

        counts = {
            topic["id"]: topic["association_count"]
            for topic in profile["topics"]
        }
        self.assertEqual(counts[policy_ids[0]], 2)
        self.assertEqual(counts[policy_ids[1]], 1)
        self.assertEqual(counts[policy_ids[2]], 1)
        self.assertAlmostEqual(
            sum(topic["share"] for topic in profile["topics"]),
            1.0,
            places=6,
        )

    def test_two_policy_topics_trigger_wholesale_campaign_fallback(self):
        policy_ids = [
            definition["id"]
            for definition in builder.POLICY_AGENDA_TOPICS
        ]
        campaign_ids = [
            definition["id"]
            for definition in builder.CAMPAIGN_AGENDA_TOPICS
        ]
        news = self.news_payload(
            policy_counts={
                policy_ids[0]: 7,
                policy_ids[1]: 5,
            },
            relevant_news=[
                self.campaign_record(
                    "Alice Observée annonce sa candidature "
                    "à l'élection présidentielle",
                    "2026-07-12T09:00:00Z",
                ),
                self.campaign_record(
                    "Alice Observée progresse dans les sondages "
                    "de la présidentielle",
                    "2026-07-20T09:00:00Z",
                ),
            ],
        )

        profile = builder.project_agenda_profiles(
            self.CANDIDATES,
            news,
        )["alice-observee"]

        self.assertEqual(profile["profile_mode"], "campaign")
        self.assertEqual(profile["association_count"], 2)
        self.assertEqual(
            [topic["id"] for topic in profile["topics"]],
            campaign_ids,
        )
        self.assertTrue(
            set(campaign_ids).isdisjoint(policy_ids)
        )

        counts = {
            topic["id"]: topic["association_count"]
            for topic in profile["topics"]
        }
        self.assertEqual(counts["candidacies_endorsements"], 1)
        self.assertEqual(counts["polls_race"], 1)
        self.assertAlmostEqual(
            sum(topic["share"] for topic in profile["topics"]),
            1.0,
            places=6,
        )

    def test_campaign_projection_respects_30_day_window_and_dedupes(self):
        news = self.news_payload(
            relevant_news=[
                self.campaign_record(
                    "Alice Observée annonce sa candidature "
                    "à l'élection présidentielle",
                    "2026-07-01T00:00:00Z",
                    ["Alice Observée", "Alice Observée"],
                ),
                self.campaign_record(
                    "Alice Observée progresse dans les sondages "
                    "de la présidentielle",
                    "2026-07-30T23:59:59Z",
                ),
                self.campaign_record(
                    "Alice Observée annonce sa candidature "
                    "à l'élection présidentielle",
                    "2026-06-30T23:59:59Z",
                ),
                self.campaign_record(
                    "Alice Observée progresse dans les sondages "
                    "de la présidentielle",
                    "2026-07-31T00:00:00Z",
                ),
            ],
        )

        profile = builder.project_agenda_profiles(
            self.CANDIDATES,
            news,
        )["alice-observee"]

        counts = {
            topic["id"]: topic["association_count"]
            for topic in profile["topics"]
        }

        self.assertEqual(profile["profile_mode"], "campaign")
        self.assertEqual(profile["association_count"], 2)
        self.assertEqual(counts["candidacies_endorsements"], 1)
        self.assertEqual(counts["polls_race"], 1)

    def test_every_candidate_receives_a_complete_profile(self):
        profiles = builder.project_agenda_profiles(
            self.CANDIDATES,
            self.news_payload(),
        )

        self.assertEqual(
            set(profiles),
            {"alice-observee", "benoit-non-teste"},
        )

        for profile in profiles.values():
            with self.subTest(profile=profile):
                self.assertEqual(profile["profile_mode"], "campaign")
                self.assertEqual(profile["window_days"], 30)
                self.assertEqual(profile["association_count"], 0)
                self.assertEqual(
                    [topic["id"] for topic in profile["topics"]],
                    [
                        definition["id"]
                        for definition in builder.CAMPAIGN_AGENDA_TOPICS
                    ],
                )
                self.assertTrue(
                    all(
                        topic["association_count"] == 0
                        and topic["share"] == 0.0
                        for topic in profile["topics"]
                    )
                )


if __name__ == "__main__":
    unittest.main()

