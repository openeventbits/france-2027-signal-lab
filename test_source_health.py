import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import source_health
from fetch_news_wire import (
    build_source_health_routes,
    generate_discovery_queries,
    generate_publisher_site_feeds,
    route_request_validators,
)


RUN_1 = datetime(2026, 7, 24, 8, tzinfo=timezone.utc)
RUN_2 = datetime(2026, 7, 24, 9, tzinfo=timezone.utc)
RUN_3 = datetime(2026, 7, 24, 10, tzinfo=timezone.utc)
RUN_4 = datetime(2026, 7, 24, 11, tzinfo=timezone.utc)


def route(
    route_id="direct:example",
    *,
    route_type="direct",
    enabled=True,
    due=True,
):
    return {
        "route_id": route_id,
        "route_type": route_type,
        "publisher": "Example Publisher",
        "domain": "example.test",
        "enabled": enabled,
        "schedule_class": "hourly",
        "schedule_slot": None,
        "due_this_run": due if enabled else False,
    }


def attempt(
    route_id="direct:example",
    *,
    success=True,
    not_modified=False,
    parsed=1,
    accepted=1,
    election=1,
    etag=None,
    last_modified=None,
    request_url="https://example.test/feed",
):
    return {
        "route_id": route_id,
        "success": success,
        "not_modified": not_modified,
        "http_status": 304 if not_modified else (200 if success else 503),
        "failure_category": None if success else "http_5xx",
        "latency_ms": 125,
        "attempts": 1,
        "response_bytes": 0 if not_modified or not success else 100,
        "etag": etag,
        "last_modified": last_modified,
        "request_url": request_url,
        "parsed_item_count": (
            0 if not_modified else (parsed if success else 0)
        ),
        "accepted_inventory_count": (
            0 if not_modified else (accepted if success else 0)
        ),
        "accepted_election_news_count": (
            0 if not_modified else (election if success else 0)
        ),
    }


def update(previous, configuration, attempts, run_at):
    return source_health.update_source_health(
        previous,
        configuration,
        attempts,
        run_at,
    )


class SourceHealthTests(unittest.TestCase):
    def test_new_route_begins_never_attempted(self):
        payload = update(None, [route(due=False)], [], RUN_1)
        record = payload["routes"][0]
        self.assertEqual(record["status"], "never_attempted")
        self.assertIsNone(record["last_attempt_at"])
        self.assertEqual(record["rolling_attempt_count"], 0)

    def test_route_not_due_preserves_attempt_history(self):
        first = update(
            None,
            [route()],
            [attempt(parsed=2, accepted=1, election=0)],
            RUN_1,
        )
        second = update(first, [route(due=False)], [], RUN_2)
        before = first["routes"][0]
        after = second["routes"][0]
        self.assertEqual(after["status"], "not_due")
        self.assertFalse(after["due_this_run"])
        for field in (
            "last_attempt_at",
            "last_success_at",
            "consecutive_failures",
            "parsed_item_count",
            "accepted_inventory_count",
            "accepted_election_news_count",
            "attempt_history",
            "rolling_attempt_count",
            "rolling_success_count",
        ):
            self.assertEqual(after[field], before[field])

    def test_route_not_due_preserves_validators(self):
        first = update(
            None,
            [route()],
            [
                attempt(
                    etag='"v1"',
                    last_modified="Wed, 22 Jul 2026 08:00:00 GMT",
                )
            ],
            RUN_1,
        )
        second = update(first, [route(due=False)], [], RUN_2)
        before = first["routes"][0]
        after = second["routes"][0]
        for field in ("etag", "last_modified", "validator_url"):
            self.assertEqual(after[field], before[field])

    def test_successful_route_resets_failures(self):
        failed = update(None, [route()], [attempt(success=False)], RUN_1)
        recovered = update(
            failed,
            [route()],
            [attempt(parsed=2, accepted=1, election=0)],
            RUN_2,
        )
        record = recovered["routes"][0]
        self.assertEqual(record["status"], "healthy")
        self.assertEqual(record["consecutive_failures"], 0)
        self.assertIsNone(record["latest_failure_category"])
        self.assertEqual(
            recovered["current_run"]["recovered_routes"],
            ["direct:example"],
        )

    def test_not_modified_resets_prior_failure_and_preserves_validators(self):
        first = update(
            None,
            [route()],
            [
                attempt(
                    etag='"v1"',
                    last_modified="Wed, 22 Jul 2026 08:00:00 GMT",
                )
            ],
            RUN_1,
        )
        failed = update(
            first,
            [route()],
            [attempt(success=False)],
            RUN_2,
        )
        recovered = update(
            failed,
            [route()],
            [attempt(not_modified=True)],
            RUN_3,
        )
        record = recovered["routes"][0]
        self.assertEqual(record["status"], "healthy_zero_yield")
        self.assertEqual(record["latest_http_status"], 304)
        self.assertTrue(record["latest_not_modified"])
        self.assertEqual(record["consecutive_failures"], 0)
        self.assertEqual(record["etag"], '"v1"')
        self.assertEqual(
            record["last_modified"],
            "Wed, 22 Jul 2026 08:00:00 GMT",
        )

    def test_failed_request_preserves_prior_validators(self):
        first = update(
            None,
            [route()],
            [attempt(etag='"v1"')],
            RUN_1,
        )
        failed = update(
            first,
            [route()],
            [attempt(success=False)],
            RUN_2,
        )
        record = failed["routes"][0]
        self.assertEqual(record["etag"], '"v1"')
        self.assertEqual(
            record["validator_url"],
            "https://example.test/feed",
        )

    def test_successful_response_updates_validators_and_diagnostics(self):
        first = update(
            None,
            [route()],
            [attempt(etag='"v1"')],
            RUN_1,
        )
        second_attempt = attempt(
            etag='"v2"',
            last_modified="Thu, 23 Jul 2026 08:00:00 GMT",
        )
        second_attempt["attempts"] = 2
        second_attempt["response_bytes"] = 321
        second = update(first, [route()], [second_attempt], RUN_2)
        record = second["routes"][0]
        self.assertEqual(record["etag"], '"v2"')
        self.assertEqual(
            record["last_modified"],
            "Thu, 23 Jul 2026 08:00:00 GMT",
        )
        self.assertEqual(record["latest_attempt_count"], 2)
        self.assertFalse(record["latest_not_modified"])
        self.assertEqual(record["response_bytes"], 321)

    def test_validators_are_not_reused_after_request_url_change(self):
        previous = update(
            None,
            [route()],
            [attempt(etag='"v1"')],
            RUN_1,
        )
        self.assertEqual(
            route_request_validators(
                previous,
                "direct:example",
                "https://example.test/feed",
            ),
            ('"v1"', None),
        )
        self.assertEqual(
            route_request_validators(
                previous,
                "direct:example",
                "https://example.test/new-feed",
            ),
            (None, None),
        )

    def test_successful_changed_url_clears_old_validators(self):
        previous = update(
            None,
            [route()],
            [attempt(etag='"v1"')],
            RUN_1,
        )
        changed = update(
            previous,
            [route()],
            [
                attempt(
                    request_url="https://example.test/new-feed",
                )
            ],
            RUN_2,
        )
        record = changed["routes"][0]
        self.assertIsNone(record["etag"])
        self.assertIsNone(record["last_modified"])
        self.assertIsNone(record["validator_url"])

    def test_successful_200_clears_omitted_old_validators(self):
        previous = update(
            None,
            [route()],
            [
                attempt(
                    etag='"v1"',
                    last_modified="Wed, 22 Jul 2026 08:00:00 GMT",
                )
            ],
            RUN_1,
        )
        refreshed = update(
            previous,
            [route()],
            [attempt()],
            RUN_2,
        )
        record = refreshed["routes"][0]
        self.assertIsNone(record["etag"])
        self.assertIsNone(record["last_modified"])
        self.assertIsNone(record["validator_url"])

    def test_published_bootstrap_without_optional_fields_remains_valid(self):
        payload = source_health.load_source_health(
            Path("source_health.json")
        )
        self.assertIsNotNone(payload)
        self.assertEqual(len(payload["routes"]), 209)
        self.assertNotIn("etag", payload["routes"][0])

    def test_one_failure_is_transient(self):
        payload = update(
            None,
            [route()],
            [attempt(success=False)],
            RUN_1,
        )
        record = payload["routes"][0]
        self.assertEqual(record["status"], "transient_failure")
        self.assertEqual(record["consecutive_failures"], 1)

    def test_threshold_failure_is_repeated(self):
        payload = None
        for run_at in (RUN_1, RUN_2, RUN_3):
            payload = update(
                payload,
                [route()],
                [attempt(success=False)],
                run_at,
            )
        record = payload["routes"][0]
        self.assertEqual(record["status"], "repeated_failure")
        self.assertEqual(
            record["consecutive_failures"],
            source_health.FAILURE_THRESHOLD,
        )
        self.assertEqual(
            payload["current_run"]["newly_repeated_failure_routes"],
            ["direct:example"],
        )

    def test_recovery_clears_repeated_failure(self):
        payload = None
        for run_at in (RUN_1, RUN_2, RUN_3):
            payload = update(
                payload,
                [route()],
                [attempt(success=False)],
                run_at,
            )
        recovered = update(
            payload,
            [route()],
            [attempt(parsed=1, accepted=0, election=0)],
            RUN_4,
        )
        record = recovered["routes"][0]
        self.assertEqual(record["status"], "healthy")
        self.assertEqual(record["consecutive_failures"], 0)
        self.assertEqual(
            recovered["current_run"]["recovered_routes"],
            ["direct:example"],
        )
        self.assertEqual(
            source_health.source_health_aggregate(recovered)[
                "repeated_failure_routes"
            ],
            0,
        )

    def test_successful_zero_item_route_is_not_failure(self):
        payload = update(
            None,
            [route()],
            [attempt(parsed=0, accepted=0, election=0)],
            RUN_1,
        )
        record = payload["routes"][0]
        self.assertEqual(record["status"], "healthy_zero_yield")
        self.assertEqual(record["consecutive_failures"], 0)
        self.assertEqual(payload["current_run"]["zero_parsed_routes"], 1)

    def test_parsed_without_election_yield_is_healthy(self):
        payload = update(
            None,
            [route()],
            [attempt(parsed=4, accepted=2, election=0)],
            RUN_1,
        )
        record = payload["routes"][0]
        self.assertEqual(record["status"], "healthy")
        self.assertEqual(record["accepted_election_news_count"], 0)
        self.assertEqual(
            payload["current_run"]["accepted_inventory_routes"],
            1,
        )
        self.assertEqual(
            payload["current_run"]["accepted_election_news_routes"],
            0,
        )

    def test_disabled_route_remains_in_history(self):
        first = update(None, [route()], [attempt()], RUN_1)
        disabled = update(
            first,
            [route(enabled=False, due=False)],
            [],
            RUN_2,
        )
        record = disabled["routes"][0]
        self.assertEqual(record["status"], "disabled")
        self.assertTrue(record["configured"])
        self.assertFalse(record["enabled"])
        self.assertEqual(record["rolling_attempt_count"], 1)

    def test_removed_route_is_retained_explicitly(self):
        first = update(None, [route()], [attempt()], RUN_1)
        removed = update(first, [], [], RUN_2)
        record = removed["routes"][0]
        self.assertEqual(record["status"], "removed")
        self.assertFalse(record["configured"])
        self.assertFalse(record["enabled"])
        self.assertEqual(record["rolling_attempt_count"], 1)

    def test_route_types_have_distinct_stable_ids(self):
        candidates = ["Alpha", "Bravo", "Charlie", "Delta"]
        configurations = build_source_health_routes(
            generate_discovery_queries(candidates),
            generate_publisher_site_feeds(),
            RUN_1,
        )
        later_configurations = build_source_health_routes(
            generate_discovery_queries(candidates),
            generate_publisher_site_feeds(),
            RUN_2,
        )
        route_ids = {record["route_id"] for record in configurations}
        self.assertEqual(
            route_ids,
            {
                record["route_id"] for record in later_configurations
            },
        )
        self.assertIn("direct:bfmtv-politique", route_ids)
        self.assertIn("discovery:france-2027-general", route_ids)
        self.assertIn("publisher-site:bfmtv.com", route_ids)
        self.assertEqual(len(route_ids), len(configurations))
        by_type = {
            route_type: {
                record["route_id"]
                for record in configurations
                if record["route_type"] == route_type
            }
            for route_type in source_health.ROUTE_TYPES
        }
        self.assertTrue(
            by_type["direct"].isdisjoint(by_type["shared_discovery"])
        )
        self.assertTrue(
            by_type["direct"].isdisjoint(by_type["publisher_site"])
        )
        self.assertTrue(
            by_type["shared_discovery"].isdisjoint(
                by_type["publisher_site"]
            )
        )

    def test_output_order_is_deterministic(self):
        configurations = [
            route("publisher-site:z.test", route_type="publisher_site"),
            route("direct:a"),
            route(
                "discovery:m",
                route_type="shared_discovery",
            ),
        ]
        attempts = [
            attempt("discovery:m"),
            attempt("publisher-site:z.test"),
            attempt("direct:a"),
        ]
        payload = update(None, configurations, attempts, RUN_1)
        self.assertEqual(
            [record["route_id"] for record in payload["routes"]],
            ["direct:a", "discovery:m", "publisher-site:z.test"],
        )

    def test_atomic_output_keeps_last_good_file_on_replace_failure(self):
        payload = update(None, [route(due=False)], [], RUN_1)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "source_health.json"
            target.write_text('{"sentinel": true}\n', encoding="utf-8")
            with patch.object(
                source_health.os,
                "replace",
                side_effect=OSError("simulated replace failure"),
            ):
                with self.assertRaises(OSError):
                    source_health.write_source_health_atomic(target, payload)
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                '{"sentinel": true}\n',
            )
            self.assertEqual(
                list(Path(directory).glob(".source_health.json.*.tmp")),
                [],
            )

            source_health.write_source_health_atomic(target, payload)
            written = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(written, payload)

    def test_malformed_previous_state_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "source_health.json"
            malformed = "{not json\n"
            target.write_text(malformed, encoding="utf-8")
            with self.assertRaisesRegex(
                source_health.SourceHealthError,
                "malformed JSON",
            ):
                source_health.load_source_health(target)
            self.assertEqual(target.read_text(encoding="utf-8"), malformed)

    def test_source_health_module_has_no_network_fetch(self):
        module_text = Path(source_health.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urlopen", module_text)
        self.assertNotIn("request_bytes", module_text)
        self.assertNotIn("requests.", module_text)

    def test_timestamp_only_change_is_not_substantive(self):
        first = update(None, [route(due=False)], [], RUN_1)
        second = update(first, [route(due=False)], [], RUN_2)
        self.assertNotEqual(first["generated_at"], second["generated_at"])
        self.assertFalse(
            source_health.has_substantive_change(first, second)
        )

    def test_rolling_window_is_bounded_and_deterministic(self):
        payload = None
        for index in range(source_health.ROLLING_ATTEMPT_LIMIT + 3):
            run_at = datetime(
                2026,
                7,
                1 + index,
                tzinfo=timezone.utc,
            )
            payload = update(
                payload,
                [route()],
                [attempt(parsed=2, accepted=1, election=0)],
                run_at,
            )
        record = payload["routes"][0]
        self.assertEqual(
            record["rolling_attempt_count"],
            source_health.ROLLING_ATTEMPT_LIMIT,
        )
        self.assertEqual(
            record["rolling_parsed_items"],
            source_health.ROLLING_ATTEMPT_LIMIT * 2,
        )


if __name__ == "__main__":
    unittest.main()
