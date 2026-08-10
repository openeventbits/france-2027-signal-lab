from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from pathlib import Path

from candidate_attention_contract import (
    validate_candidate_attention,
)

from build_candidate_attention import (
    EVENT_AMPLIFIED_DIFFERENCE_MIN_PCT,
    EVENT_AMPLIFIED_PEAK_SHARE_MIN,
    EVENT_AMPLIFIED_RAW_MIN_PCT,
    EVENT_AMPLIFIED_RETAINED_RATIO_MAX,
    LOW_BASE_7D_VIEWS,
    SUSTAINED_CHANGE_MIN_PCT,
    CandidateAttentionBuildError,
    atomic_write_bytes,
    build_candidate_attention_payload,
    calculate_candidate_metrics,
    interpretation_flag,
    percentage_change,
    serialize_semantic_payload,
    validate_daily_series,
    WikimediaFetchError,
    WikimediaPageviewsNotFoundError,
    collect_wikimedia_observations,
    fetch_json,
    fetch_pageview_series,
    run_build,
    verify_article_mapping,
)


ROOT = Path(__file__).resolve().parent

CANDIDACY = json.loads(
    (
        ROOT
        / "candidate_candidacy_status.json"
    ).read_text(
        encoding="utf-8"
    )
)

REGISTRY = json.loads(
    (
        ROOT
        / "wikimedia_candidate_articles.json"
    ).read_text(
        encoding="utf-8"
    )
)

DATA_AS_OF = date(
    2026,
    8,
    6,
)


def series_from_views(
    views,
    *,
    data_as_of=DATA_AS_OF,
):
    if len(views) != 90:
        raise ValueError(
            "fixture must contain 90 values"
        )

    start = (
        data_as_of
        - timedelta(days=89)
    )

    return [
        {
            "date": (
                start
                + timedelta(days=index)
            ).isoformat(),
            "views": value,
        }
        for index, value in enumerate(
            views
        )
    ]


def constant_series(
    value=100,
):
    return series_from_views(
        [value] * 90
    )


def complete_observations(
    value=100,
):
    return {
        candidate["candidate_id"]:
            constant_series(value)
        for candidate
        in CANDIDACY["candidates"]
    }


def flag_metrics(
    *,
    latest_7_views=10000,
    raw=0.0,
    adjusted=0.0,
    peak_share=0.20,
):
    return {
        "latest_7_views":
            latest_7_views,
        "change_7_pct":
            raw,
        "change_7_peak_removed_pct":
            adjusted,
        "latest_7_peak_share":
            peak_share,
    }


class CandidateAttentionCalculationTests(
    unittest.TestCase
):
    def test_percentage_change(self):
        self.assertEqual(
            percentage_change(120, 100),
            20.0,
        )
        self.assertEqual(
            percentage_change(75, 100),
            -25.0,
        )
        self.assertIsNone(
            percentage_change(10, 0)
        )

    def test_metrics_use_exact_seven_and_28_day_windows(self):
        views = [10] * 90

        views[-56:-28] = [20] * 28
        views[-28:-14] = [30] * 14
        views[-14:-7] = [40] * 7
        views[-7:] = [50] * 7

        metrics = (
            calculate_candidate_metrics(
                series_from_views(
                    views
                ),
                data_as_of=DATA_AS_OF,
            )
        )

        self.assertEqual(
            metrics["latest_7_views"],
            350,
        )
        self.assertEqual(
            metrics["previous_7_views"],
            280,
        )
        self.assertEqual(
            metrics["change_7_pct"],
            25.0,
        )

        self.assertEqual(
            metrics["latest_28_views"],
            1050,
        )
        self.assertEqual(
            metrics["previous_28_views"],
            560,
        )
        self.assertEqual(
            metrics["change_28_pct"],
            87.5,
        )

    def test_peak_removed_comparison_removes_one_peak_per_window(self):
        views = [100] * 90

        views[-14:-7] = [
            100,
            100,
            100,
            100,
            100,
            100,
            700,
        ]

        views[-7:] = [
            100,
            100,
            100,
            100,
            100,
            100,
            1900,
        ]

        metrics = (
            calculate_candidate_metrics(
                series_from_views(
                    views
                ),
                data_as_of=DATA_AS_OF,
            )
        )

        self.assertEqual(
            metrics["previous_7_views"],
            1300,
        )
        self.assertEqual(
            metrics["latest_7_views"],
            2500,
        )

        self.assertEqual(
            metrics[
                "change_7_peak_removed_pct"
            ],
            0.0,
        )

    def test_peak_tie_uses_earliest_date(self):
        metrics = (
            calculate_candidate_metrics(
                constant_series(100),
                data_as_of=DATA_AS_OF,
            )
        )

        self.assertEqual(
            metrics[
                "latest_7_peak_date"
            ],
            (
                DATA_AS_OF
                - timedelta(days=6)
            ).isoformat(),
        )

        self.assertEqual(
            metrics[
                "period_peak_date"
            ],
            (
                DATA_AS_OF
                - timedelta(days=89)
            ).isoformat(),
        )

    def test_zero_series_uses_null_percentages(self):
        metrics = (
            calculate_candidate_metrics(
                constant_series(0),
                data_as_of=DATA_AS_OF,
            )
        )

        self.assertIsNone(
            metrics["change_7_pct"]
        )
        self.assertIsNone(
            metrics["change_28_pct"]
        )
        self.assertIsNone(
            metrics[
                "latest_7_peak_share"
            ]
        )
        self.assertIsNone(
            metrics[
                "change_7_peak_removed_pct"
            ]
        )

    def test_missing_date_is_rejected_before_calculation(self):
        series = constant_series()
        series[20]["date"] = (
            series[21]["date"]
        )

        with self.assertRaises(
            CandidateAttentionBuildError
        ):
            validate_daily_series(
                series,
                data_as_of=DATA_AS_OF,
            )

    def test_negative_view_is_rejected_before_calculation(self):
        series = constant_series()
        series[20]["views"] = -1

        with self.assertRaises(
            CandidateAttentionBuildError
        ):
            validate_daily_series(
                series,
                data_as_of=DATA_AS_OF,
            )


class CandidateAttentionInterpretationTests(
    unittest.TestCase
):
    def test_threshold_constants_are_locked(self):
        self.assertEqual(
            LOW_BASE_7D_VIEWS,
            3000,
        )
        self.assertEqual(
            SUSTAINED_CHANGE_MIN_PCT,
            5.0,
        )
        self.assertEqual(
            EVENT_AMPLIFIED_RAW_MIN_PCT,
            10.0,
        )
        self.assertEqual(
            EVENT_AMPLIFIED_DIFFERENCE_MIN_PCT,
            15.0,
        )
        self.assertEqual(
            EVENT_AMPLIFIED_RETAINED_RATIO_MAX,
            0.40,
        )
        self.assertEqual(
            EVENT_AMPLIFIED_PEAK_SHARE_MIN,
            0.35,
        )

    def test_low_base_precedes_all_other_flags(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    latest_7_views=2999,
                    raw=100.0,
                    adjusted=100.0,
                    peak_share=0.10,
                )
            ),
            "low_base",
        )

    def test_exact_low_base_boundary_is_not_low_base(self):
        self.assertNotEqual(
            interpretation_flag(
                flag_metrics(
                    latest_7_views=3000,
                    raw=0.0,
                    adjusted=0.0,
                )
            ),
            "low_base",
        )

    def test_stable_under_five_percent_boundary(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    raw=4.9,
                    adjusted=4.9,
                )
            ),
            "stable",
        )

    def test_exact_five_percent_supported_rise_is_sustained(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    raw=5.0,
                    adjusted=5.0,
                )
            ),
            "sustained_rise",
        )

    def test_exact_minus_five_supported_decline_is_sustained(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    raw=-5.0,
                    adjusted=-5.0,
                )
            ),
            "sustained_decline",
        )

    def test_attal_like_change_is_sustained_rise(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    raw=39.3,
                    adjusted=35.6,
                    peak_share=0.196,
                )
            ),
            "sustained_rise",
        )

    def test_glucksmann_like_change_remains_sustained(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    raw=130.0,
                    adjusted=107.5,
                    peak_share=0.280,
                )
            ),
            "sustained_rise",
        )

    def test_le_pen_like_change_is_event_amplified(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    raw=18.0,
                    adjusted=1.3,
                    peak_share=0.275,
                )
            ),
            "event_amplified",
        )

    def test_sign_reversal_is_event_amplified(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    raw=20.0,
                    adjusted=-1.0,
                    peak_share=0.20,
                )
            ),
            "event_amplified",
        )

    def test_high_peak_share_with_collapsed_adjusted_change_is_event_amplified(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    raw=12.0,
                    adjusted=4.0,
                    peak_share=0.35,
                )
            ),
            "event_amplified",
        )

    def test_large_difference_without_material_collapse_is_sustained(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    raw=40.0,
                    adjusted=24.0,
                    peak_share=0.20,
                )
            ),
            "sustained_rise",
        )

    def test_division_by_zero_change_is_stable_above_low_base(self):
        self.assertEqual(
            interpretation_flag(
                flag_metrics(
                    latest_7_views=5000,
                    raw=None,
                    adjusted=None,
                )
            ),
            "stable",
        )


class CandidateAttentionPayloadTests(
    unittest.TestCase
):
    def test_complete_payload_passes_public_contract(self):
        payload = (
            build_candidate_attention_payload(
                candidacy_payload=CANDIDACY,
                registry_payload=REGISTRY,
                observations_by_candidate=(
                    complete_observations()
                ),
                generated_at=(
                    "2026-08-07T05:00:00Z"
                ),
                data_as_of="2026-08-06",
            )
        )

        validate_candidate_attention(
            payload,
            expected_candidates=(
                CANDIDACY["candidates"]
            ),
        )

        self.assertEqual(
            len(payload["candidates"]),
            20,
        )

    def test_candidate_order_is_candidacy_order_not_attention_order(self):
        observations = (
            complete_observations()
        )

        candidate_ids = [
            candidate["candidate_id"]
            for candidate
            in CANDIDACY["candidates"]
        ]

        observations[
            candidate_ids[-1]
        ] = constant_series(9999)

        payload = (
            build_candidate_attention_payload(
                candidacy_payload=CANDIDACY,
                registry_payload=REGISTRY,
                observations_by_candidate=observations,
                generated_at=(
                    "2026-08-07T05:00:00Z"
                ),
                data_as_of="2026-08-06",
            )
        )

        self.assertEqual(
            [
                candidate[
                    "candidate_id"
                ]
                for candidate
                in payload["candidates"]
            ],
            candidate_ids,
        )

    def test_missing_candidate_observations_are_rejected(self):
        observations = (
            complete_observations()
        )
        observations.pop(
            next(iter(observations))
        )

        with self.assertRaises(
            CandidateAttentionBuildError
        ):
            build_candidate_attention_payload(
                candidacy_payload=CANDIDACY,
                registry_payload=REGISTRY,
                observations_by_candidate=observations,
                generated_at=(
                    "2026-08-07T05:00:00Z"
                ),
                data_as_of="2026-08-06",
            )

    def test_semantic_serialization_ignores_execution_timestamp_only(self):
        first = (
            build_candidate_attention_payload(
                candidacy_payload=CANDIDACY,
                registry_payload=REGISTRY,
                observations_by_candidate=(
                    complete_observations()
                ),
                generated_at=(
                    "2026-08-07T05:00:00Z"
                ),
                data_as_of="2026-08-06",
            )
        )

        second = copy.deepcopy(
            first
        )

        second["generated_at"] = (
            "2026-08-07T06:00:00Z"
        )

        self.assertEqual(
            serialize_semantic_payload(
                first
            ),
            serialize_semantic_payload(
                second
            ),
        )

    def test_semantic_serialization_detects_observation_change(self):
        first = (
            build_candidate_attention_payload(
                candidacy_payload=CANDIDACY,
                registry_payload=REGISTRY,
                observations_by_candidate=(
                    complete_observations()
                ),
                generated_at=(
                    "2026-08-07T05:00:00Z"
                ),
                data_as_of="2026-08-06",
            )
        )

        observations = (
            complete_observations()
        )

        first_id = (
            CANDIDACY[
                "candidates"
            ][0]["candidate_id"]
        )

        observations[
            first_id
        ][-1]["views"] += 1

        second = (
            build_candidate_attention_payload(
                candidacy_payload=CANDIDACY,
                registry_payload=REGISTRY,
                observations_by_candidate=observations,
                generated_at=(
                    "2026-08-07T05:00:00Z"
                ),
                data_as_of="2026-08-06",
            )
        )

        self.assertNotEqual(
            serialize_semantic_payload(
                first
            ),
            serialize_semantic_payload(
                second
            ),
        )


class CandidateAttentionAtomicWriteTests(
    unittest.TestCase
):
    def test_atomic_write_replaces_complete_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = (
                root
                / "candidate_attention.json"
            )

            target.write_bytes(
                b"old\n"
            )

            atomic_write_bytes(
                target,
                b"new complete content\n",
            )

            self.assertEqual(
                target.read_bytes(),
                b"new complete content\n",
            )

            leftovers = [
                path
                for path in root.iterdir()
                if (
                    path.name.startswith(
                        ".candidate_attention.json."
                    )
                    and path.suffix == ".tmp"
                )
            ]

            self.assertEqual(
                leftovers,
                [],
            )


class FakeResponse:
    def __init__(
        self,
        *,
        payload=None,
        raw=None,
        status=200,
        headers=None,
    ):
        self.status = status
        self.headers = (
            headers
            or {}
        )

        if raw is not None:
            self.body = raw
        else:
            self.body = json.dumps(
                payload,
                ensure_ascii=False,
            ).encode(
                "utf-8"
            )

        self.offset = 0
        self.closed = False

    def getcode(
        self,
    ):
        return self.status

    def read(
        self,
        size=-1,
    ):
        if (
            size is None
            or size < 0
        ):
            size = (
                len(
                    self.body
                )
                - self.offset
            )

        chunk = self.body[
            self.offset:
            self.offset
            + size
        ]

        self.offset += (
            len(
                chunk
            )
        )

        return chunk

    def close(
        self,
    ):
        self.closed = True


def action_payload(
    title,
):
    return {
        "query": {
            "pages": [
                {
                    "pageid": 1,
                    "title": title,
                }
            ]
        }
    }


def pageview_payload(
    *,
    data_as_of=DATA_AS_OF,
    value=100,
):
    start = (
        data_as_of
        - timedelta(
            days=89
        )
    )

    return {
        "items": [
            {
                "timestamp": (
                    start
                    + timedelta(
                        days=index
                    )
                ).strftime(
                    "%Y%m%d00"
                ),
                "views": value,
            }
            for index
            in range(
                90
            )
        ]
    }


class CandidateAttentionHttpTests(
    unittest.TestCase
):
    def test_identifying_user_agent_and_json_accept_header_are_sent(
        self,
    ):
        captured = {}

        def opener(
            request,
            timeout,
        ):
            captured[
                "user_agent"
            ] = request.get_header(
                "User-agent"
            )

            captured[
                "accept"
            ] = request.get_header(
                "Accept"
            )

            captured[
                "timeout"
            ] = timeout

            return FakeResponse(
                payload={
                    "ok": True
                }
            )

        result = fetch_json(
            "https://example.invalid/test",
            opener=opener,
        )

        self.assertEqual(
            result,
            {
                "ok": True
            },
        )

        self.assertIn(
            "France2027SignalLab",
            captured[
                "user_agent"
            ],
        )

        self.assertIn(
            "github.com/openeventbits/"
            "france-2027-signal-lab",
            captured[
                "user_agent"
            ],
        )

        self.assertEqual(
            captured[
                "accept"
            ],
            "application/json",
        )

        self.assertEqual(
            captured[
                "timeout"
            ],
            20,
        )

    def test_429_retry_after_then_success(
        self,
    ):
        calls = []
        sleeps = []

        def opener(
            request,
            timeout,
        ):
            calls.append(
                request.full_url
            )

            if len(calls) == 1:
                raise HTTPError(
                    request.full_url,
                    429,
                    (
                        "Too Many "
                        "Requests"
                    ),
                    {
                        "Retry-After":
                        "0"
                    },
                    None,
                )

            return FakeResponse(
                payload={
                    "ok": True
                }
            )

        result = fetch_json(
            "https://example.invalid/test",
            opener=opener,
            sleeper=(
                sleeps.append
            ),
        )

        self.assertEqual(
            result,
            {
                "ok": True
            },
        )

        self.assertEqual(
            len(
                calls
            ),
            2,
        )

        self.assertEqual(
            sleeps,
            [
                0.0
            ],
        )

    def test_non_retryable_404_fails_immediately(
        self,
    ):
        calls = []

        def opener(
            request,
            timeout,
        ):
            calls.append(
                request.full_url
            )

            raise HTTPError(
                request.full_url,
                404,
                "Not Found",
                {},
                None,
            )

        with self.assertRaises(
            WikimediaFetchError
        ) as context:
            fetch_json(
                "https://example.invalid/test",
                opener=opener,
                sleeper=(
                    lambda _:
                    None
                ),
            )

        self.assertEqual(
            context.exception.category,
            "http_4xx",
        )

        self.assertEqual(
            context.exception.status,
            404,
        )

        self.assertEqual(
            context.exception.attempts,
            1,
        )

        self.assertEqual(
            len(
                calls
            ),
            1,
        )

    def test_network_failure_is_bounded(
        self,
    ):
        calls = []
        sleeps = []

        def opener(
            request,
            timeout,
        ):
            calls.append(
                request.full_url
            )

            raise URLError(
                "offline"
            )

        with self.assertRaises(
            WikimediaFetchError
        ) as context:
            fetch_json(
                "https://example.invalid/test",
                opener=opener,
                sleeper=(
                    sleeps.append
                ),
            )

        self.assertEqual(
            context.exception.category,
            "network_error",
        )

        self.assertEqual(
            context.exception.attempts,
            4,
        )

        self.assertEqual(
            len(
                calls
            ),
            4,
        )

        self.assertEqual(
            len(
                sleeps
            ),
            3,
        )

    def test_malformed_json_is_rejected(
        self,
    ):
        def opener(
            request,
            timeout,
        ):
            return FakeResponse(
                raw=b"{not-json"
            )

        with self.assertRaises(
            WikimediaFetchError
        ) as context:
            fetch_json(
                "https://example.invalid/test",
                opener=opener,
            )

        self.assertEqual(
            context.exception.category,
            "malformed_json",
        )

    def test_response_size_limit_is_enforced(
        self,
    ):
        def opener(
            request,
            timeout,
        ):
            return FakeResponse(
                raw=(
                    b"x"
                    * 20
                )
            )

        with self.assertRaises(
            WikimediaFetchError
        ) as context:
            fetch_json(
                "https://example.invalid/test",
                opener=opener,
                max_response_bytes=10,
            )

        self.assertEqual(
            context.exception.category,
            "response_too_large",
        )


class CandidateAttentionTitleTests(
    unittest.TestCase
):
    def test_normal_mapping_resolves_to_controlled_title(
        self,
    ):
        mapping = next(
            item
            for item
            in REGISTRY[
                "candidates"
            ]
            if item[
                "candidate_id"
            ]
            == "gabriel-attal"
        )

        def fetcher(
            url,
        ):
            return action_payload(
                "Gabriel Attal"
            )

        self.assertEqual(
            verify_article_mapping(
                mapping,
                fetcher=fetcher,
            ),
            "Gabriel Attal",
        )

    def test_olivier_requested_title_does_not_replace_canonical_title(
        self,
    ):
        from urllib.parse import (
            parse_qs,
            urlsplit,
        )

        mapping = next(
            item
            for item
            in REGISTRY[
                "candidates"
            ]
            if item[
                "candidate_id"
            ]
            == "olivier-faure"
        )

        titles = []

        def fetcher(
            url,
        ):
            title = (
                parse_qs(
                    urlsplit(
                        url
                    ).query
                )["titles"][0]
            )

            titles.append(
                title
            )

            return action_payload(
                title
            )

        self.assertEqual(
            verify_article_mapping(
                mapping,
                fetcher=fetcher,
            ),
            (
                "Olivier Faure "
                "(homme politique)"
            ),
        )

        self.assertEqual(
            titles,
            [
                (
                    "Olivier Faure "
                    "(homme politique)"
                ),
                "Olivier Faure",
            ],
        )

    def test_unexpected_canonical_redirect_is_rejected(
        self,
    ):
        mapping = next(
            item
            for item
            in REGISTRY[
                "candidates"
            ]
            if item[
                "candidate_id"
            ]
            == "gabriel-attal"
        )

        def fetcher(
            url,
        ):
            return action_payload(
                "Unexpected title"
            )

        with self.assertRaises(
            CandidateAttentionBuildError
        ):
            verify_article_mapping(
                mapping,
                fetcher=fetcher,
            )


class CandidateAttentionPageviewCollectionTests(
    unittest.TestCase
):
    def test_first_attempt_success_has_no_retry_sleep(
        self,
    ):
        calls = []
        sleeps = []

        def fetcher(url):
            calls.append(url)
            return pageview_payload(value=123)

        series = fetch_pageview_series(
            "Gabriel Attal",
            data_as_of=DATA_AS_OF,
            fetcher=fetcher,
            sleeper=sleeps.append,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])
        self.assertEqual(len(series), 90)

    def test_one_404_retries_same_url_then_succeeds(
        self,
    ):
        calls = []
        sleeps = []

        def fetcher(url):
            calls.append(url)

            if len(calls) == 1:
                raise WikimediaFetchError(
                    "http_4xx",
                    "HTTP 404",
                    status=404,
                    attempts=1,
                )

            return pageview_payload(value=123)

        with redirect_stdout(io.StringIO()):
            series = fetch_pageview_series(
                "Gabriel Attal",
                data_as_of=DATA_AS_OF,
                fetcher=fetcher,
                sleeper=sleeps.append,
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(len(set(calls)), 1)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(len(series), 90)

    def test_two_404s_retry_same_url_then_succeed(
        self,
    ):
        calls = []
        sleeps = []

        def fetcher(url):
            calls.append(url)

            if len(calls) < 3:
                raise WikimediaFetchError(
                    "http_4xx",
                    "HTTP 404",
                    status=404,
                    attempts=1,
                )

            return pageview_payload(value=123)

        with redirect_stdout(io.StringIO()):
            series = fetch_pageview_series(
                "Gabriel Attal",
                data_as_of=DATA_AS_OF,
                fetcher=fetcher,
                sleeper=sleeps.append,
            )

        self.assertEqual(len(calls), 3)
        self.assertEqual(len(set(calls)), 1)
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertEqual(len(series), 90)

    def test_three_404s_raise_after_bounded_retries_with_diagnostics(
        self,
    ):
        calls = []
        sleeps = []
        output = io.StringIO()

        def fetcher(url):
            calls.append(url)
            raise WikimediaFetchError(
                "http_4xx",
                "HTTP 404",
                status=404,
                attempts=1,
            )

        with self.assertRaises(
            WikimediaPageviewsNotFoundError
        ) as context:
            with redirect_stdout(output):
                fetch_pageview_series(
                    "Gabriel Attal",
                    data_as_of=DATA_AS_OF,
                    fetcher=fetcher,
                    sleeper=sleeps.append,
                )

        self.assertEqual(len(calls), 3)
        self.assertEqual(len(set(calls)), 1)
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertEqual(context.exception.attempts, 3)
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "Pageviews HTTP 404; retrying same "
                "request (2/3) after 1s.",
                "Pageviews HTTP 404; retrying same "
                "request (3/3) after 2s.",
            ],
        )

    def test_exact_ninety_day_series_is_accepted(
        self,
    ):
        series = (
            fetch_pageview_series(
                "Gabriel Attal",
                data_as_of=(
                    DATA_AS_OF
                ),
                fetcher=(
                    lambda _:
                    pageview_payload(
                        value=123
                    )
                ),
            )
        )

        self.assertEqual(
            len(
                series
            ),
            90,
        )

        self.assertEqual(
            series[0][
                "date"
            ],
            "2026-05-09",
        )

        self.assertEqual(
            series[-1][
                "date"
            ],
            "2026-08-06",
        )

        self.assertTrue(
            all(
                item[
                    "views"
                ] == 123
                for item
                in series
            )
        )

    def test_returned_zero_is_preserved(
        self,
    ):
        payload = (
            pageview_payload(
                value=100
            )
        )

        payload[
            "items"
        ][10][
            "views"
        ] = 0

        series = (
            fetch_pageview_series(
                "Gabriel Attal",
                data_as_of=(
                    DATA_AS_OF
                ),
                fetcher=(
                    lambda _:
                    payload
                ),
            )
        )

        self.assertEqual(
            series[10][
                "views"
            ],
            0,
        )

    def test_missing_day_is_not_zero_filled(
        self,
    ):
        payload = (
            pageview_payload()
        )

        payload[
            "items"
        ].pop(
            10
        )

        calls = []
        sleeps = []

        def fetcher(url):
            calls.append(url)
            return payload

        with self.assertRaises(
            CandidateAttentionBuildError
        ):
            fetch_pageview_series(
                "Gabriel Attal",
                data_as_of=(
                    DATA_AS_OF
                ),
                fetcher=(
                    fetcher
                ),
                sleeper=(
                    sleeps.append
                ),
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])

    def test_duplicate_day_is_rejected(
        self,
    ):
        payload = (
            pageview_payload()
        )

        payload[
            "items"
        ][11][
            "timestamp"
        ] = (
            payload[
                "items"
            ][10][
                "timestamp"
            ]
        )

        with self.assertRaises(
            CandidateAttentionBuildError
        ):
            fetch_pageview_series(
                "Gabriel Attal",
                data_as_of=(
                    DATA_AS_OF
                ),
                fetcher=(
                    lambda _:
                    payload
                ),
            )

    def test_negative_views_are_rejected(
        self,
    ):
        payload = (
            pageview_payload()
        )

        payload[
            "items"
        ][10][
            "views"
        ] = -1

        with self.assertRaises(
            CandidateAttentionBuildError
        ):
            fetch_pageview_series(
                "Gabriel Attal",
                data_as_of=(
                    DATA_AS_OF
                ),
                fetcher=(
                    lambda _:
                    payload
                ),
            )

    def test_collection_is_sequential_and_ordered(
        self,
    ):
        from urllib.parse import (
            parse_qs,
            urlsplit,
        )

        calls = []
        sleeps = []

        def fetcher(
            url,
        ):
            calls.append(
                url
            )

            if (
                "/w/api.php?"
                in url
            ):
                title = (
                    parse_qs(
                        urlsplit(
                            url
                        ).query
                    )[
                        "titles"
                    ][0]
                )

                return action_payload(
                    title
                )

            return (
                pageview_payload()
            )

        result = (
            collect_wikimedia_observations(
                candidacy_payload=(
                    CANDIDACY
                ),
                registry_payload=(
                    REGISTRY
                ),
                data_as_of=(
                    DATA_AS_OF
                ),
                fetcher=(
                    fetcher
                ),
                delay_seconds=0.01,
                sleeper=(
                    sleeps.append
                ),
            )
        )

        expected_ids = [
            candidate[
                "candidate_id"
            ]
            for candidate
            in CANDIDACY[
                "candidates"
            ]
        ]

        self.assertEqual(
            list(
                result
            ),
            expected_ids,
        )

        # 20 canonical checks
        # + Olivier requested title check
        # + 20 pageview calls
        self.assertEqual(
            len(
                calls
            ),
            41,
        )

        self.assertEqual(
            len(
                sleeps
            ),
            40,
        )

        source = (
            ROOT
            / "build_candidate_attention.py"
        ).read_text(
            encoding="utf-8"
        )

        for forbidden in (
            "ThreadPoolExecutor",
            "asyncio.gather",
            "multiprocessing.Pool",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )


class CandidateAttentionAvailabilityFallbackTests(
    unittest.TestCase
):
    @staticmethod
    def _request_data_as_of(
        url,
    ):
        return datetime.strptime(
            url.rstrip("/").rsplit("/", 1)[-1],
            "%Y%m%d",
        ).date()

    @classmethod
    def _success_for_url(
        cls,
        url,
        *,
        value=137,
    ):
        if "/w/api.php?" in url:
            title = parse_qs(
                urlsplit(url).query
            )["titles"][0]
            return action_payload(title)

        return pageview_payload(
            data_as_of=cls._request_data_as_of(url),
            value=value,
        )

    def _run_build(
        self,
        fetcher,
        *,
        fallback_days=1,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate_attention.json"

            with redirect_stdout(io.StringIO()):
                return run_build(
                    candidacy_path=(
                        ROOT / "candidate_candidacy_status.json"
                    ),
                    registry_path=(
                        ROOT / "wikimedia_candidate_articles.json"
                    ),
                    output_path=output,
                    data_as_of=DATA_AS_OF.isoformat(),
                    generated_at="2026-08-07T05:00:00Z",
                    fallback_days=fallback_days,
                    delay_seconds=0,
                    fetcher=fetcher,
                    sleeper=lambda _: None,
                )

    def test_preferred_date_success_does_not_fallback(
        self,
    ):
        pageview_dates = []

        def fetcher(url):
            if "/w/api.php?" not in url:
                pageview_dates.append(
                    self._request_data_as_of(url)
                )
            return self._success_for_url(url)

        payload = self._run_build(fetcher)

        self.assertEqual(
            payload["period"]["data_as_of"],
            DATA_AS_OF.isoformat(),
        )
        self.assertEqual(
            pageview_dates,
            [DATA_AS_OF] * 20,
        )

    def test_pageviews_404_rebuilds_complete_previous_date(
        self,
    ):
        previous = DATA_AS_OF - timedelta(days=1)
        pageview_dates = []
        verification_calls = 0

        def fetcher(url):
            nonlocal verification_calls

            if "/w/api.php?" in url:
                verification_calls += 1
                return self._success_for_url(url)

            requested_date = self._request_data_as_of(url)
            pageview_dates.append(requested_date)

            if requested_date == DATA_AS_OF:
                raise WikimediaFetchError(
                    "http_4xx",
                    "HTTP 404",
                    status=404,
                    attempts=1,
                )

            return self._success_for_url(url)

        payload = self._run_build(fetcher)

        self.assertEqual(
            pageview_dates,
            [DATA_AS_OF] * 3 + [previous] * 20,
        )
        self.assertEqual(
            verification_calls,
            22,
        )
        self.assertEqual(
            payload["candidate_universe"]["count"],
            20,
        )
        self.assertEqual(
            len(payload["candidates"]),
            20,
        )
        self.assertEqual(
            payload["period"]["data_as_of"],
            previous.isoformat(),
        )
        self.assertTrue(
            all(
                len(candidate["daily_series"]) == 90
                for candidate in payload["candidates"]
            )
        )
        self.assertTrue(
            all(
                observation["views"] == 137
                for candidate in payload["candidates"]
                for observation in candidate["daily_series"]
            )
        )

    def test_pageviews_404_on_both_dates_fails_closed(
        self,
    ):
        requested_dates = []

        def fetcher(url):
            if "/w/api.php?" in url:
                return self._success_for_url(url)

            requested_dates.append(
                self._request_data_as_of(url)
            )
            raise WikimediaFetchError(
                "http_4xx",
                "HTTP 404",
                status=404,
                attempts=1,
            )

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "candidate_attention.json"
            target.write_bytes(b"last-good\n")

            with self.assertRaises(WikimediaFetchError):
                with redirect_stdout(io.StringIO()):
                    run_build(
                        candidacy_path=(
                            ROOT / "candidate_candidacy_status.json"
                        ),
                        registry_path=(
                            ROOT / "wikimedia_candidate_articles.json"
                        ),
                        output_path=target,
                        data_as_of=DATA_AS_OF.isoformat(),
                        generated_at="2026-08-07T05:00:00Z",
                        fallback_days=1,
                        delay_seconds=0,
                        fetcher=fetcher,
                        sleeper=lambda _: None,
                    )

            self.assertEqual(
                target.read_bytes(),
                b"last-good\n",
            )

        self.assertEqual(
            requested_dates,
            [DATA_AS_OF] * 3
            + [DATA_AS_OF - timedelta(days=1)] * 3,
        )

    def test_pageviews_fallback_is_disabled_by_default(
        self,
    ):
        pageview_dates = []

        def fetcher(url):
            if "/w/api.php?" in url:
                return self._success_for_url(url)

            pageview_dates.append(
                self._request_data_as_of(url)
            )
            raise WikimediaFetchError(
                "http_4xx",
                "HTTP 404",
                status=404,
                attempts=1,
            )

        with self.assertRaises(WikimediaFetchError):
            self._run_build(
                fetcher,
                fallback_days=0,
            )

        self.assertEqual(
            pageview_dates,
            [DATA_AS_OF] * 3,
        )

    def test_verification_404_does_not_trigger_fallback(
        self,
    ):
        calls = []

        def fetcher(url):
            calls.append(url)
            raise WikimediaFetchError(
                "http_4xx",
                "HTTP 404",
                status=404,
                attempts=1,
            )

        with self.assertRaises(WikimediaFetchError):
            self._run_build(fetcher)

        self.assertEqual(len(calls), 1)
        self.assertIn("/w/api.php?", calls[0])

    def test_non_404_pageviews_failures_do_not_trigger_fallback(
        self,
    ):
        cases = (
            ("network_error", None),
            ("timeout", None),
            ("rate_limited", 429),
            ("http_5xx", 503),
        )

        for category, status in cases:
            with self.subTest(category=category):
                pageview_dates = []

                def fetcher(url):
                    if "/w/api.php?" in url:
                        return self._success_for_url(url)

                    pageview_dates.append(
                        self._request_data_as_of(url)
                    )
                    raise WikimediaFetchError(
                        category,
                        "simulated failure",
                        status=status,
                        attempts=4,
                    )

                with self.assertRaises(WikimediaFetchError):
                    self._run_build(fetcher)

                self.assertEqual(
                    pageview_dates,
                    [DATA_AS_OF],
                )

    def test_incomplete_pageviews_payload_does_not_fallback(
        self,
    ):
        pageview_dates = []

        def fetcher(url):
            if "/w/api.php?" in url:
                return self._success_for_url(url)

            requested_date = self._request_data_as_of(url)
            pageview_dates.append(requested_date)
            payload = pageview_payload(
                data_as_of=requested_date
            )
            payload["items"].pop()
            return payload

        with self.assertRaises(CandidateAttentionBuildError):
            self._run_build(fetcher)

        self.assertEqual(
            pageview_dates,
            [DATA_AS_OF],
        )

    def test_failure_diagnostics_end_with_candidate_and_phase(
        self,
    ):
        output = io.StringIO()

        def fetcher(url):
            if "/w/api.php?" in url:
                return self._success_for_url(url)

            raise WikimediaFetchError(
                "network_error",
                "offline",
                attempts=4,
            )

        with self.assertRaises(WikimediaFetchError):
            with redirect_stdout(output):
                collect_wikimedia_observations(
                    candidacy_payload=CANDIDACY,
                    registry_payload=REGISTRY,
                    data_as_of=DATA_AS_OF,
                    fetcher=fetcher,
                    delay_seconds=0,
                    sleeper=lambda _: None,
                )

        lines = output.getvalue().splitlines()
        self.assertEqual(
            lines,
            [
                "[01/20] Bruno Retailleau "
                "(bruno-retailleau) - verify",
                "[01/20] Bruno Retailleau "
                "(bruno-retailleau) - pageviews",
            ],
        )


class CandidateAttentionOutputSafetyTests(
    unittest.TestCase
):
    def test_failed_collection_preserves_existing_output(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(
                temporary
            )

            target = (
                root
                / "candidate_attention.json"
            )

            target.write_bytes(
                b"last-good\n"
            )

            def failing_fetcher(
                url,
            ):
                raise WikimediaFetchError(
                    "network_error",
                    (
                        "simulated "
                        "failure"
                    ),
                    attempts=4,
                )

            with self.assertRaises(
                WikimediaFetchError
            ):
                run_build(
                    candidacy_path=(
                        ROOT
                        / (
                            "candidate_"
                            "candidacy_status.json"
                        )
                    ),
                    registry_path=(
                        ROOT
                        / (
                            "wikimedia_"
                            "candidate_articles.json"
                        )
                    ),
                    output_path=(
                        target
                    ),
                    data_as_of=(
                        "2026-08-06"
                    ),
                    generated_at=(
                        "2026-08-07T05:00:00Z"
                    ),
                    delay_seconds=0,
                    fetcher=(
                        failing_fetcher
                    ),
                    sleeper=(
                        lambda _:
                        None
                    ),
                )

            self.assertEqual(
                target.read_bytes(),
                b"last-good\n",
            )


if __name__ == "__main__":
    unittest.main()