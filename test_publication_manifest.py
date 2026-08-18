import hashlib
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import build_campaign_events as campaign_builder
import build_publication_manifest as manifest_builder
import source_health
from campaign_events_contract import serialize_campaign_events


ROOT = Path(__file__).resolve().parent
PUBLISHED_AT = "2026-07-25T10:00:00Z"


def write_json(root, name, payload):
    (root / name).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def candidate_signals_payload():
    return json.loads(
        (ROOT / "candidate_signals.json").read_text(encoding="utf-8")
    )



def candidate_visibility_history_payload():
    return json.loads(
        (
            ROOT
            / "candidate_visibility_history.json"
        ).read_text(encoding="utf-8")
    )


def legacy_candidate_attention_payload():
    """Return a deterministic, self-contained schema-1.0 fixture."""

    from datetime import date, timedelta

    from candidate_attention_contract import (
        METHODOLOGY_INTERPRETATION,
        METHODOLOGY_LABEL,
        METHODOLOGY_NOT_MEASURES,
        METHODOLOGY_REDIRECT_LIMITATION,
        METHODOLOGY_WEEKLY_COMPARISON,
    )

    start = date(2026, 5, 9)
    dates = [
        start + timedelta(days=offset)
        for offset in range(90)
    ]

    def percentage_change(current, previous):
        if previous == 0:
            return None
        return round(
            ((current - previous) / previous) * 100.0,
            1,
        )

    def candidate_payload(
        candidate_id,
        candidate_name,
        article_slug,
        daily_views,
    ):
        series = [
            {
                "date": day.isoformat(),
                "views": daily_views,
            }
            for day in dates
        ]

        latest_7 = series[-7:]
        previous_7 = series[-14:-7]
        latest_28 = series[-28:]
        previous_28 = series[-56:-28]

        latest_7_views = sum(
            item["views"]
            for item in latest_7
        )
        previous_7_views = sum(
            item["views"]
            for item in previous_7
        )
        latest_28_views = sum(
            item["views"]
            for item in latest_28
        )
        previous_28_views = sum(
            item["views"]
            for item in previous_28
        )

        latest_peak = max(
            latest_7,
            key=lambda item: item["views"],
        )
        previous_peak = max(
            previous_7,
            key=lambda item: item["views"],
        )
        period_peak = max(
            series,
            key=lambda item: item["views"],
        )

        current_without_peak = (
            latest_7_views
            - latest_peak["views"]
        )
        previous_without_peak = (
            previous_7_views
            - previous_peak["views"]
        )

        return {
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "canonical_article": candidate_name,
            "article_url": (
                "https://fr.wikipedia.org/wiki/"
                f"{article_slug}"
            ),
            "latest_7_views": latest_7_views,
            "previous_7_views": previous_7_views,
            "change_7_pct": percentage_change(
                latest_7_views,
                previous_7_views,
            ),
            "latest_28_views": latest_28_views,
            "previous_28_views": previous_28_views,
            "change_28_pct": percentage_change(
                latest_28_views,
                previous_28_views,
            ),
            "latest_7_peak_date": (
                latest_peak["date"]
            ),
            "latest_7_peak_views": (
                latest_peak["views"]
            ),
            "latest_7_peak_share": round(
                latest_peak["views"]
                / latest_7_views,
                4,
            ),
            "change_7_peak_removed_pct": (
                percentage_change(
                    current_without_peak,
                    previous_without_peak,
                )
            ),
            "period_peak_date": (
                period_peak["date"]
            ),
            "period_peak_views": (
                period_peak["views"]
            ),
            "interpretation_flag": "stable",
            "daily_series": series,
        }

    end = dates[-1]

    candidates = [
        candidate_payload(
            "candidate-a",
            "Candidate A",
            "Candidate_A",
            10,
        ),
        candidate_payload(
            "candidate-b",
            "Candidate B",
            "Candidate_B",
            20,
        ),
    ]

    return {
        "schema_version": "1.0",
        "generated_at": "2026-08-07T04:42:05Z",
        "source": {
            "project": "fr.wikipedia.org",
            "api": "Wikimedia Analytics API",
            "metric": "pageviews",
            "access": "all-access",
            "agent": "user",
            "granularity": "daily",
        },
        "period": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": 90,
            "data_as_of": end.isoformat(),
        },
        "candidate_universe": {
            "source": "candidate_candidacy_status.json",
            "status_as_of": "2026-07-30",
            "count": 2,
        },
        "methodology": {
            "label": METHODOLOGY_LABEL,
            "interpretation": (
                METHODOLOGY_INTERPRETATION
            ),
            "not_measures": list(
                METHODOLOGY_NOT_MEASURES
            ),
            "weekly_comparison": (
                METHODOLOGY_WEEKLY_COMPARISON
            ),
            "redirect_limitation": (
                METHODOLOGY_REDIRECT_LIMITATION
            ),
        },
        "validation": {
            "status": "pass",
            "candidate_count": 2,
            "expected_days_per_candidate": 90,
            "missing_dates": 0,
            "duplicate_dates": 0,
        },
        "candidates": candidates,
    }


def serialized_manifest(payload):
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )


def canonical_newlines(content):
    return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def canonical_source_bytes(path):
    return canonical_newlines(path.read_bytes())


def complete_inputs(root):
    source_news = json.loads(
        (ROOT / "news_wire.json").read_text(encoding="utf-8")
    )
    write_json(root, "candidate_signals.json", candidate_signals_payload())
    write_json(
        root,
        "candidate_candidacy_status.json",
        json.loads(
            (ROOT / "candidate_candidacy_status.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    write_json(
        root,
        "candidate_attention.json",
        json.loads(
            (ROOT / "candidate_attention.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    write_json(
        root,
        "candidate_visibility_history.json",
        candidate_visibility_history_payload(),
    )
    write_json(
        root,
        "campaign_events.json",
        {
            "schema_version": "1.1",
            "generated_at": "2026-08-01T00:00:00Z",
            "data_as_of": "2026-08-01T00:00:00Z",
            "campaign_events": [],
            "institutional_milestones": [],
            "event_watch": [],
        },
    )
    write_json(
        root,
        "polls.json",
        [
            {"fieldwork_end": "2026-07-09"},
            {"fieldwork_end": "2026-07-10"},
        ],
    )
    write_json(
        root,
        "second_round_polls.json",
        {
            "schema_version": "1.0",
            "generated_at": "2026-07-22T17:01:45Z",
            "events": [
                {"fieldwork_end": "2026-07-07"},
                {"fieldwork_end": "2026-07-08"},
            ],
        },
    )
    write_json(
        root,
        "closest_tested_runoff.json",
        {
            "schema_version": "1.0",
            "generated_at": "2026-07-22T17:01:45Z",
            "status": "agree",
        },
    )
    write_json(
        root,
        "news_wire.json",
        {
            "schema_version": 1,
            "generated_at": "2026-07-25T08:03:00Z",
            "discovery": {
                "approved_publisher_domains": 202,
            },
            "feed_coverage": {
                "configured_media_publishers": 180,
                "configured_feeds": 209,
                "feeds_due_this_run": 53,
                "feeds_successful_this_run": 52,
                "contributing_publishers_30d": 86,
            },
            "election_news": [
                {
                    "publisher": "Publisher A",
                    "published_at": "2026-07-25T06:00:00Z",
                },
                {
                    "publisher": "Publisher B",
                    "published_at": "2026-07-25T06:04:00Z",
                },
            ],
            "notable_developments": [],
            "relevant_news": [],
            "candidate_visibility": source_news["candidate_visibility"],
            "candidate_watch": source_news["candidate_watch"],
        },
    )
    write_json(
        root,
        "claims_under_scrutiny.json",
        {
            "schema_version": 1,
            "generated_at": "2026-07-17T12:00:19Z",
            "reviews": [
                {"review_date": "2026-07-16"},
                {"review_date": "2026-07-17"},
            ],
        },
    )
    write_json(
        root,
        "recent_changes.json",
        {
            "schema_version": 1,
            "generated_at": "2026-07-25T08:04:00Z",
            "last_successful_check_at": "2026-07-25T08:04:00Z",
            "items": [
                {"trusted_change_at": "2026-07-22T11:11:10Z"},
                {"trusted_change_at": "2026-07-21"},
            ],
        },
    )
    health_routes = [
        {
            "route_id": f"direct:route-{index}",
            "route_type": "direct",
            "publisher": f"Publisher {index}",
            "domain": f"publisher-{index}.test",
            "enabled": True,
            "schedule_class": "hourly",
            "schedule_slot": None,
            "due_this_run": True,
        }
        for index in range(1, 5)
    ]

    def health_attempt(route_id, success, parsed=1):
        return {
            "route_id": route_id,
            "success": success,
            "http_status": 200 if success else 503,
            "failure_category": None if success else "http_error",
            "latency_ms": 100,
            "parsed_item_count": parsed if success else 0,
            "accepted_inventory_count": parsed if success else 0,
            "accepted_election_news_count": 0,
        }

    health_payload = None
    for run_at, route_four_success in (
        ("2026-07-25T08:00:00Z", False),
        ("2026-07-25T09:00:00Z", False),
        ("2026-07-25T10:00:00Z", True),
    ):
        health_payload = source_health.update_source_health(
            health_payload,
            health_routes,
            [
                health_attempt("direct:route-1", True),
                health_attempt("direct:route-2", False),
                health_attempt("direct:route-3", True, parsed=0),
                health_attempt(
                    "direct:route-4",
                    route_four_success,
                ),
            ],
            run_at,
        )
    write_json(root, "source_health.json", health_payload)


class PublicationManifestTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / f".publication-manifest-test-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        complete_inputs(self.root)

    def build(self, published_at=PUBLISHED_AT):
        return manifest_builder.build_manifest(
            self.root,
            published_at=published_at,
        )

    def candidate_payload(self):
        return json.loads(
            (self.root / "candidate_signals.json").read_text(
                encoding="utf-8"
            )
        )

    def test_deterministic_snapshot_id(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertRegex(first["snapshot_id"], r"^[0-9a-f]{64}$")

    def test_snapshot_id_is_independent_of_published_at(self):
        first = self.build("2026-07-25T10:00:00Z")
        second = self.build("2026-07-25T11:00:00Z")
        self.assertNotEqual(first["published_at"], second["published_at"])
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])

    def test_valid_complete_inputs(self):
        manifest = self.build()
        self.assertEqual(manifest["schema_version"], "1.4")
        self.assertEqual(manifest["published_at"], PUBLISHED_AT)
        self.assertEqual(
            set(manifest["lanes"]),
            {
                "candidacy_status",
                "campaign_events",
                "candidate_attention",
                "candidate_signals",
                "candidate_visibility_history",
                "polls",
                "runoff",
                "news",
                "claims",
                "recent_changes",
                "source_health",
            },
        )
        self.assertEqual(manifest["warnings"], [])
        for lane in manifest["lanes"].values():
            self.assertTrue(lane["available"])
            self.assertTrue(lane["valid"])
            self.assertRegex(lane["sha256"], r"^[0-9a-f]{64}$")


    def test_candidate_visibility_history_lane_metadata(self):
        manifest = self.build()

        lane = manifest["lanes"][
            "candidate_visibility_history"
        ]

        source = (
            self.root
            / "candidate_visibility_history.json"
        )

        source_payload = json.loads(
            source.read_text(
                encoding="utf-8"
            )
        )

        canonical = canonical_source_bytes(
            source
        )

        self.assertEqual(
            lane["file"],
            "candidate_visibility_history.json",
        )

        self.assertTrue(
            lane["available"]
        )

        self.assertTrue(
            lane["valid"]
        )

        self.assertEqual(
            lane["schema_version"],
            "1.0",
        )

        self.assertEqual(
            lane["data_as_of"],
            source_payload[
                "period"
            ]["data_as_of"],
        )

        self.assertEqual(
            lane["timestamp_status"],
            "unknown",
        )

        self.assertEqual(
            lane["record_count"],
            len(
                source_payload[
                    "candidates"
                ]
            ),
        )

        self.assertEqual(
            lane["byte_size"],
            len(canonical),
        )

        self.assertEqual(
            lane["sha256"],
            hashlib.sha256(
                canonical
            ).hexdigest(),
        )


    def test_candidate_visibility_history_candidacy_parity(self):
        source = (
            self.root
            / "candidate_visibility_history.json"
        )

        payload = json.loads(
            source.read_text(
                encoding="utf-8"
            )
        )

        payload["candidates"][0][
            "candidate_name"
        ] += " Changed"

        write_json(
            self.root,
            "candidate_visibility_history.json",
            payload,
        )

        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate_visibility_history candidacy parity",
        ):
            self.build()


    def test_candidacy_status_lane_metadata(self):
        manifest = self.build()
        lane = manifest["lanes"]["candidacy_status"]
        source = self.root / "candidate_candidacy_status.json"
        source_payload = json.loads(
            source.read_text(encoding="utf-8")
        )
        self.assertEqual(
            list(manifest["lanes"]),
            [
                "campaign_events",
                "candidacy_status",
                "candidate_attention",
                "candidate_signals",
                "candidate_visibility_history",
                "claims",
                "news",
                "polls",
                "recent_changes",
                "runoff",
                "source_health",
            ],
        )
        self.assertEqual(lane["file"], "candidate_candidacy_status.json")
        self.assertTrue(lane["available"])
        self.assertTrue(lane["valid"])
        self.assertEqual(
            lane["schema_version"],
            source_payload["schema_version"],
        )
        self.assertEqual(
            lane["data_as_of"],
            source_payload["status_as_of"],
        )
        self.assertEqual(lane["timestamp_status"], "known")
        self.assertEqual(
            lane["record_count"],
            len(source_payload["candidates"]),
        )
        self.assertEqual(
            lane["candidate_total"],
            len(source_payload["candidates"]),
        )

        tier_counts = {
            tier: sum(
                candidate["display_tier"] == tier
                for candidate in source_payload["candidates"]
            )
            for tier in ("main", "secondary", "hidden")
        }
        self.assertEqual(lane["main_total"], tier_counts["main"])
        self.assertEqual(
            lane["secondary_total"],
            tier_counts["secondary"],
        )
        self.assertEqual(lane["hidden_total"], tier_counts["hidden"])
        self.assertEqual(
            lane["candidate_total"],
            sum(tier_counts.values()),
        )

        expected_active = sum(
            candidate["display_tier"] in {"main", "secondary"}
            and candidate.get("upstream_presence", "present") == "present"
            for candidate in source_payload["candidates"]
        )
        self.assertEqual(lane["active_total"], expected_active)
        self.assertEqual(
            lane["temporarily_missing_total"],
            sum(
                candidate.get("upstream_presence", "present")
                == "temporarily_missing"
                for candidate in source_payload["candidates"]
            ),
        )

        self.assertRegex(lane["semantic_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            lane["status_as_of"],
            source_payload["status_as_of"],
        )

        source_metadata = source_payload["source"]
        self.assertEqual(
            lane["wikipedia_revision_id"],
            source_metadata["revision_id"],
        )
        self.assertEqual(
            lane["wikipedia_revision_timestamp"],
            source_metadata["revision_timestamp"],
        )
        self.assertEqual(
            lane["canonical_source_url"],
            source_metadata["page_url"],
        )
        self.assertEqual(lane["warnings"], [])
        self.assertEqual(
            lane["sha256"],
            hashlib.sha256(canonical_source_bytes(source)).hexdigest(),
        )

    def production_inputs_root(self, name):
        destination = self.root / name
        destination.mkdir()
        for file_names in manifest_builder.LANE_FILES.values():
            for filename in file_names:
                shutil.copy2(ROOT / filename, destination / filename)
        return destination

    def manifest_inputs_with_newlines(self, name, newline):
        destination = self.production_inputs_root(name)
        for file_names in manifest_builder.LANE_FILES.values():
            for filename in file_names:
                source = destination / filename
                source.write_bytes(
                    canonical_source_bytes(source).replace(b"\n", newline)
                )
        return destination

    def test_lf_and_crlf_sources_have_identical_manifest_metadata(self):
        lf_root = self.manifest_inputs_with_newlines("lf-inputs", b"\n")
        crlf_root = self.manifest_inputs_with_newlines(
            "crlf-inputs", b"\r\n"
        )
        crlf_before = {
            filename: (crlf_root / filename).read_bytes()
            for file_names in manifest_builder.LANE_FILES.values()
            for filename in file_names
        }

        lf_manifest = manifest_builder.build_manifest(
            lf_root,
            published_at=PUBLISHED_AT,
        )
        crlf_manifest = manifest_builder.build_manifest(
            crlf_root,
            published_at=PUBLISHED_AT,
        )

        self.assertEqual(lf_manifest, crlf_manifest)
        self.assertEqual(
            lf_manifest["snapshot_id"], crlf_manifest["snapshot_id"]
        )
        self.assertEqual(
            lf_manifest["lanes"]["campaign_events"]["byte_size"],
            crlf_manifest["lanes"]["campaign_events"]["byte_size"],
        )
        self.assertEqual(
            crlf_before,
            {
                filename: (crlf_root / filename).read_bytes()
                for file_names in manifest_builder.LANE_FILES.values()
                for filename in file_names
            },
        )

    def test_lone_cr_sources_match_lf_manifest_metadata(self):
        lf_root = self.manifest_inputs_with_newlines("lone-cr-lf", b"\n")
        cr_root = self.manifest_inputs_with_newlines("lone-cr", b"\r")

        self.assertEqual(
            manifest_builder.build_manifest(lf_root, published_at=PUBLISHED_AT),
            manifest_builder.build_manifest(cr_root, published_at=PUBLISHED_AT),
        )

    def test_non_newline_byte_changes_remain_digest_significant(self):
        baseline = self.build()

        def assert_changed(filename, lane_name, content):
            source = self.root / filename
            original = source.read_bytes()
            source.write_bytes(content)
            try:
                changed = self.build()
            finally:
                source.write_bytes(original)
            self.assertNotEqual(
                changed["lanes"][lane_name]["sha256"],
                baseline["lanes"][lane_name]["sha256"],
            )
            self.assertNotEqual(changed["snapshot_id"], baseline["snapshot_id"])

        polls_path = self.root / "polls.json"
        polls = json.loads(polls_path.read_text(encoding="utf-8"))
        changed_value = json.loads(json.dumps(polls))
        changed_value[-1]["fieldwork_end"] = "2026-07-11"
        assert_changed(
            "polls.json",
            "polls",
            json.dumps(changed_value, ensure_ascii=False).encode("utf-8"),
        )
        assert_changed(
            "polls.json",
            "polls",
            json.dumps(
                polls,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )

        claims_path = self.root / "claims_under_scrutiny.json"
        claims = json.loads(claims_path.read_text(encoding="utf-8"))
        reordered_claims = dict(reversed(list(claims.items())))
        self.assertEqual(reordered_claims, claims)
        assert_changed(
            "claims_under_scrutiny.json",
            "claims",
            json.dumps(reordered_claims, ensure_ascii=False).encode("utf-8"),
        )
        assert_changed(
            "polls.json",
            "polls",
            polls_path.read_bytes() + b"\n",
        )

    def test_non_utf8_source_remains_invalid_and_lane_isolated(self):
        baseline = self.build()
        source = self.root / "claims_under_scrutiny.json"
        undecodable = b'{"schema_version": 1, "value": "\xff"}'
        source.write_bytes(undecodable)

        manifest = self.build()
        lane = manifest["lanes"]["claims"]
        self.assertTrue(lane["available"])
        self.assertFalse(lane["valid"])
        self.assertEqual(
            lane["sha256"],
            hashlib.sha256(canonical_newlines(undecodable)).hexdigest(),
        )
        self.assertTrue(
            any("malformed JSON" in warning for warning in lane["warnings"])
        )
        self.assertEqual(source.read_bytes(), undecodable)
        self.assertEqual(
            {
                name: value
                for name, value in manifest["lanes"].items()
                if name != "claims"
            },
            {
                name: value
                for name, value in baseline["lanes"].items()
                if name != "claims"
            },
        )

    def test_manifest_construction_does_not_rewrite_sources(self):
        before = {
            filename: (self.root / filename).read_bytes()
            for file_names in manifest_builder.LANE_FILES.values()
            for filename in file_names
        }
        self.build()
        after = {
            filename: (self.root / filename).read_bytes()
            for file_names in manifest_builder.LANE_FILES.values()
            for filename in file_names
        }
        self.assertEqual(after, before)

    def test_campaign_events_lane_metadata(self):
        manifest = self.build()
        lane = manifest["lanes"]["campaign_events"]
        source = self.root / "campaign_events.json"
        self.assertEqual(lane["file"], "campaign_events.json")
        self.assertTrue(lane["available"])
        self.assertTrue(lane["valid"])
        self.assertEqual(lane["schema_version"], "1.1")
        self.assertEqual(lane["generated_at"], "2026-08-01T00:00:00Z")
        self.assertEqual(lane["data_as_of"], "2026-08-01T00:00:00Z")
        self.assertEqual(lane["timestamp_status"], "known")
        self.assertEqual(lane["record_count"], 0)
        self.assertEqual(lane["byte_size"], len(canonical_source_bytes(source)))
        self.assertEqual(
            lane["sha256"],
            hashlib.sha256(canonical_source_bytes(source)).hexdigest(),
        )
        self.assertEqual(lane["warnings"], [])

    def test_tracked_campaign_events_lane_metadata(self):
        tracked_manifest = json.loads(
            (ROOT / "publication_manifest.json").read_text(encoding="utf-8")
        )
        tracked_campaign = json.loads(
            (ROOT / "campaign_events.json").read_text(encoding="utf-8")
        )
        rebuilt = manifest_builder.build_manifest(
            ROOT,
            published_at=tracked_manifest["published_at"],
        )
        lane = rebuilt["lanes"]["campaign_events"]
        source = ROOT / "campaign_events.json"
        self.assertEqual(
            lane, tracked_manifest["lanes"]["campaign_events"]
        )
        self.assertEqual(lane["file"], "campaign_events.json")
        self.assertTrue(lane["available"])
        self.assertTrue(lane["valid"])
        self.assertEqual(lane["schema_version"], tracked_campaign["schema_version"])
        self.assertEqual(lane["generated_at"], tracked_campaign["generated_at"])
        self.assertEqual(lane["data_as_of"], tracked_campaign["data_as_of"])
        self.assertEqual(
            lane["record_count"],
            len(tracked_campaign["campaign_events"])
            + len(tracked_campaign["institutional_milestones"])
            + len(tracked_campaign["event_watch"]),
        )
        self.assertEqual(lane["byte_size"], len(canonical_source_bytes(source)))
        self.assertEqual(
            lane["sha256"],
            hashlib.sha256(canonical_source_bytes(source)).hexdigest(),
        )
        self.assertEqual(lane["timestamp_status"], "known")
        self.assertEqual(lane["warnings"], [])

    def test_tracked_legacy_bundle_remains_buildable_without_rewriting_manifest(self):
        tracked_path = ROOT / "publication_manifest.json"
        tracked = json.loads(tracked_path.read_text(encoding="utf-8"))
        rebuilt = manifest_builder.build_manifest(
            ROOT,
            published_at=tracked["published_at"],
        )
        self.assertEqual(rebuilt, manifest_builder.build_manifest(
            ROOT,
            published_at=tracked["published_at"],
        ))
        self.assertEqual(
            rebuilt["lanes"]["campaign_events"]["sha256"],
            tracked["lanes"]["campaign_events"]["sha256"],
        )

    def test_manual_workflow_no_churn_sequence_matches_both_tracked_outputs(self):
        production_root = self.production_inputs_root("workflow-no-churn")

        for filename in (
            "campaign_event_institutional_seeds.json",
            "campaign_event_sources.json",
            "campaign_events_manual.json",
            "campaign_event_updates_manual.json",
        ):
            shutil.copy2(
                ROOT / filename,
                production_root / filename,
            )

        campaign_path = production_root / "campaign_events.json"
        baseline_generated_at = "2098-01-01T00:00:00Z"
        later_generated_at = "2099-01-01T00:00:00Z"

        campaign_builder.build_from_paths(
            generated_at=baseline_generated_at,
            seed_path=(
                production_root
                / "campaign_event_institutional_seeds.json"
            ),
            source_registry_path=(
                production_root
                / "campaign_event_sources.json"
            ),
            candidate_registry_path=(
                production_root
                / "candidate_candidacy_status.json"
            ),
            manual_events_path=(
                production_root
                / "campaign_events_manual.json"
            ),
            event_updates_path=(
                production_root
                / "campaign_event_updates_manual.json"
            ),
            output_path=campaign_path,
        )

        baseline_campaign = json.loads(
            campaign_path.read_text(encoding="utf-8")
        )
        baseline_bytes = canonical_source_bytes(campaign_path)
        baseline_manifest = manifest_builder.build_manifest(
            production_root,
            published_at=PUBLISHED_AT,
        )

        self.assertGreater(
            later_generated_at,
            baseline_campaign["generated_at"],
        )

        campaign_builder.build_from_paths(
            generated_at=later_generated_at,
            seed_path=(
                production_root
                / "campaign_event_institutional_seeds.json"
            ),
            source_registry_path=(
                production_root
                / "campaign_event_sources.json"
            ),
            candidate_registry_path=(
                production_root
                / "candidate_candidacy_status.json"
            ),
            manual_events_path=(
                production_root
                / "campaign_events_manual.json"
            ),
            event_updates_path=(
                production_root
                / "campaign_event_updates_manual.json"
            ),
            output_path=campaign_path,
            preserve_generated_at_from=campaign_path,
        )

        rebuilt_campaign = json.loads(
            campaign_path.read_text(encoding="utf-8")
        )

        self.assertEqual(
            rebuilt_campaign["generated_at"],
            baseline_campaign["generated_at"],
        )
        self.assertEqual(
            rebuilt_campaign["data_as_of"],
            baseline_campaign["data_as_of"],
        )
        self.assertEqual(
            rebuilt_campaign["campaign_events"],
            baseline_campaign["campaign_events"],
        )
        self.assertEqual(
            rebuilt_campaign["institutional_milestones"],
            baseline_campaign["institutional_milestones"],
        )
        self.assertEqual(
            rebuilt_campaign["event_watch"],
            baseline_campaign["event_watch"],
        )
        self.assertEqual(
            canonical_source_bytes(campaign_path),
            baseline_bytes,
        )

        rebuilt_manifest = manifest_builder.build_manifest(
            production_root,
            published_at=PUBLISHED_AT,
        )

        self.assertEqual(
            rebuilt_manifest,
            baseline_manifest,
        )

    def test_genuine_campaign_events_change_updates_digest_and_snapshot(self):
        production_root = self.production_inputs_root("campaign-change")
        tracked_manifest = json.loads(
            (ROOT / "publication_manifest.json").read_text(encoding="utf-8")
        )
        baseline = manifest_builder.build_manifest(
            production_root,
            published_at=tracked_manifest["published_at"],
        )
        changed = json.loads(
            (ROOT / "campaign_events.json").read_text(encoding="utf-8")
        )
        changed["institutional_milestones"][0]["title"] += " — mise à jour"
        (production_root / "campaign_events.json").write_bytes(
            serialize_campaign_events(changed)
        )
        rebuilt = manifest_builder.build_manifest(
            production_root,
            published_at=tracked_manifest["published_at"],
        )
        self.assertNotEqual(
            rebuilt["lanes"]["campaign_events"]["sha256"],
            tracked_manifest["lanes"]["campaign_events"]["sha256"],
        )
        self.assertNotEqual(rebuilt["snapshot_id"], tracked_manifest["snapshot_id"])
        self.assertEqual(
            {
                name: lane
                for name, lane in rebuilt["lanes"].items()
                if name != "campaign_events"
            },
            {
                name: lane
                for name, lane in baseline["lanes"].items()
                if name != "campaign_events"
            },
        )

    def test_missing_campaign_events_is_isolated_to_its_lane(self):
        baseline = self.build()
        (self.root / "campaign_events.json").unlink()
        manifest = self.build()
        lane = manifest["lanes"]["campaign_events"]
        self.assertFalse(lane["available"])
        self.assertFalse(lane["valid"])
        self.assertTrue(any("campaign_events.json is missing" in item for item in lane["warnings"]))
        self.assertTrue(any("campaign_events.json is missing" in item for item in manifest["warnings"]))
        self.assertEqual(
            {name: value for name, value in manifest["lanes"].items() if name != "campaign_events"},
            {name: value for name, value in baseline["lanes"].items() if name != "campaign_events"},
        )

    def test_malformed_campaign_events_is_isolated_to_its_lane(self):
        baseline = self.build()
        (self.root / "campaign_events.json").write_text(
            "{not json",
            encoding="utf-8",
        )
        manifest = self.build()
        lane = manifest["lanes"]["campaign_events"]
        self.assertTrue(lane["available"])
        self.assertFalse(lane["valid"])
        self.assertTrue(any("campaign_events.json is malformed JSON" in item for item in lane["warnings"]))
        self.assertTrue(any("campaign_events.json is malformed JSON" in item for item in manifest["warnings"]))
        self.assertEqual(
            {name: value for name, value in manifest["lanes"].items() if name != "campaign_events"},
            {name: value for name, value in baseline["lanes"].items() if name != "campaign_events"},
        )

    def test_missing_or_malformed_candidacy_registry_fails(self):
        registry_path = self.root / "candidate_candidacy_status.json"
        registry_path.unlink()
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate_candidacy_status.json is missing",
        ):
            self.build()
        write_json(self.root, "candidate_candidacy_status.json", {})
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidacy_status invalid structure",
        ):
            self.build()

    def test_registry_candidate_signals_parity_is_required(self):
        payload = self.candidate_payload()
        payload["candidates"][0]["candidacy"][
            "active_field_eligible"
        ] = not payload["candidates"][0]["candidacy"][
            "active_field_eligible"
        ]
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaises(manifest_builder.ManifestError):
            self.build()

    def test_valid_registry_and_projection_change_changes_snapshot_id(self):
        first = self.build()["snapshot_id"]
        registry_path = self.root / "candidate_candidacy_status.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        payload = self.candidate_payload()
        changed_id = registry["candidates"][0]["candidate_id"]
        registry["candidates"][0]["status_note"] += " Updated."
        next(
            candidate
            for candidate in payload["candidates"]
            if candidate["candidate_id"] == changed_id
        )["candidacy"]["status_note"] += " Updated."
        write_json(self.root, "candidate_candidacy_status.json", registry)
        write_json(self.root, "candidate_signals.json", payload)
        self.assertNotEqual(first, self.build()["snapshot_id"])


    def test_candidate_attention_lane_metadata(self):
        manifest = self.build()
        lane = manifest["lanes"]["candidate_attention"]
        source = self.root / "candidate_attention.json"
        payload = json.loads(
            source.read_text(encoding="utf-8")
        )

        self.assertEqual(
            lane["file"],
            "candidate_attention.json",
        )
        self.assertTrue(lane["available"])
        self.assertTrue(lane["valid"])
        self.assertEqual(
            lane["schema_version"],
            payload["schema_version"],
        )
        self.assertEqual(
            lane["schema_version"],
            "1.1",
        )
        self.assertEqual(
            lane["generated_at"],
            payload["generated_at"],
        )
        self.assertEqual(
            lane["data_as_of"],
            payload["period"]["data_as_of"],
        )
        self.assertNotEqual(
            lane["data_as_of"],
            payload["generated_at"][:10],
        )
        self.assertEqual(
            lane["timestamp_status"],
            "known",
        )
        self.assertEqual(
            lane["record_count"],
            len(payload["candidates"]),
        )
        self.assertEqual(
            lane["sha256"],
            hashlib.sha256(
                canonical_source_bytes(source)
            ).hexdigest(),
        )
        self.assertEqual(
            lane["warnings"],
            [],
        )

    def test_candidate_attention_participates_in_snapshot_id(self):
        first = self.build()["snapshot_id"]

        path = self.root / "candidate_attention.json"
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )

        payload["generated_at"] = (
            "2026-08-07T09:00:00Z"
        )

        write_json(
            self.root,
            "candidate_attention.json",
            payload,
        )

        self.assertNotEqual(
            first,
            self.build()["snapshot_id"],
        )

    def test_missing_candidate_attention_fails(self):
        (
            self.root
            / "candidate_attention.json"
        ).unlink()

        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate_attention.json is missing",
        ):
            self.build()

    def test_malformed_candidate_attention_json_fails(self):
        (
            self.root
            / "candidate_attention.json"
        ).write_text(
            "{not json",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate_attention.json is malformed JSON",
        ):
            self.build()

    def test_invalid_candidate_attention_structure_fails_cleanly(self):
        path = self.root / "candidate_attention.json"

        payload = json.loads(
            path.read_text(encoding="utf-8")
        )

        payload["period"]["days"] = 89

        write_json(
            self.root,
            "candidate_attention.json",
            payload,
        )

        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate_attention invalid structure",
        ):
            self.build()


    def test_legacy_candidate_attention_name_parity_is_deferred_under_registry_v2(self):
        path = self.root / "candidate_attention.json"
        payload = legacy_candidate_attention_payload()

        payload["candidates"][0][
            "candidate_name"
        ] += " changed"

        write_json(
            self.root,
            "candidate_attention.json",
            payload,
        )

        manifest = self.build()
        self.assertTrue(
            manifest["lanes"]["candidate_attention"]["valid"]
        )


    def test_legacy_attention_is_intrinsic_during_registry_v2_migration(self):
        registry = json.loads(
            (
                self.root
                / "candidate_candidacy_status.json"
            ).read_text(encoding="utf-8")
        )

        registry["schema_version"] = "2.0"

        # Deliberately invalid current-registry metadata: legacy
        # Attention schema 1.0 is intrinsic during Registry-v2
        # migration and must return before current-registry parity.
        registry["source"] = {
            "publisher": "French Wikipedia",
            "page_title": (
                "Élection présidentielle française de 2027"
            ),
            "page_url": (
                "https://fr.wikipedia.org/wiki/"
                "Élection_présidentielle_française_de_2027"
            ),
            "revision_id": 1,
            "revision_timestamp": "2026-08-01T00:00:00Z",
            "revision_url": (
                "https://fr.wikipedia.org/w/index.php?oldid=1"
            ),
        }

        attention = legacy_candidate_attention_payload()

        manifest_builder._validate_candidate_attention_parity(
            registry,
            attention,
        )


    def test_legacy_candidate_attention_id_parity_is_deferred_under_registry_v2(self):
        payload = legacy_candidate_attention_payload()

        payload["candidates"][0][
            "candidate_id"
        ] = "different-candidate-id"

        write_json(
            self.root,
            "candidate_attention.json",
            payload,
        )

        manifest = self.build()
        self.assertTrue(
            manifest["lanes"]["candidate_attention"]["valid"]
        )


    def test_legacy_candidate_attention_order_parity_is_deferred_under_registry_v2(self):
        payload = legacy_candidate_attention_payload()

        payload["candidates"][0], payload["candidates"][1] = (
            payload["candidates"][1],
            payload["candidates"][0],
        )

        write_json(
            self.root,
            "candidate_attention.json",
            payload,
        )

        manifest = self.build()
        self.assertTrue(
            manifest["lanes"]["candidate_attention"]["valid"]
        )


    def test_candidate_attention_parity_ignores_candidacy_state(self):
        registry = json.loads(
            (
                self.root
                / "candidate_candidacy_status.json"
            ).read_text(
                encoding="utf-8"
            )
        )

        attention = legacy_candidate_attention_payload()

        registry["candidates"][0][
            "status"
        ] = "test-only-status"

        registry["candidates"][0][
            "display_tier"
        ] = "hidden"

        registry["candidates"][0][
            "status_as_of"
        ] = "2030-01-01"

        # This assertion is specifically about the legacy
        # schema-1.0 Registry-v2 migration bypass.
        manifest_builder._validate_candidate_attention_parity(
            registry,
            attention,
        )

    def test_candidate_attention_parity_wraps_bad_registry(self):
        attention = json.loads(
            (
                self.root
                / "candidate_attention.json"
            ).read_text(
                encoding="utf-8"
            )
        )

        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate_attention candidacy parity failed",
        ):
            manifest_builder._validate_candidate_attention_parity(
                {},
                attention,
            )

    def test_candidate_signals_lane_metadata(self):
        manifest = self.build()
        lane = manifest["lanes"]["candidate_signals"]
        source = self.root / "candidate_signals.json"
        source_payload = json.loads(
            source.read_text(encoding="utf-8")
        )
        self.assertEqual(lane["file"], "candidate_signals.json")
        self.assertEqual(
            lane["sha256"],
            hashlib.sha256(canonical_source_bytes(source)).hexdigest(),
        )
        self.assertEqual(
            lane["record_count"],
            len(source_payload["candidates"]),
        )
        self.assertEqual(
            lane["record_count"],
            source_payload["candidate_universe"]["count"],
        )

        evidence_dates = [
            value
            for value in source_payload["evidence_dates"].values()
            if value is not None
        ]
        self.assertTrue(evidence_dates)
        self.assertEqual(lane["data_as_of"], max(evidence_dates))
        registry_payload = json.loads(
            (
                self.root / "candidate_candidacy_status.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            source_payload["candidate_universe"]["status_as_of"],
            registry_payload["status_as_of"],
        )

    def test_active_field_projection_matches_record_level_news(self):
        payload = self.candidate_payload()
        news = json.loads(
            (self.root / "news_wire.json").read_text(encoding="utf-8")
        )
        active = payload["active_field_visibility"]
        complete_field = payload["presidential_field"]
        active_field = payload["active_monitoring_field"]
        active_names = {
            candidate["candidate_name"]
            for candidate in payload["candidates"]
            if candidate["candidacy"]["active_field_eligible"]
        }
        scope_rules = {
            "primary": {"election", "campaign"},
            "general": {"general"},
        }
        for scope_name, coverage_scopes in scope_rules.items():
            scope = active[scope_name]
            publishers_by_period = {}
            for period_name in ("current_period", "prior_period"):
                period = scope[period_name]
                matching = [
                    record for record in news["candidate_watch"]
                    if period["start_date"] <= record["published_at"][:10] <= period["end_date"]
                    and record["coverage_scope"] in coverage_scopes
                    and active_names & set(record["candidates"])
                ]
                records_by_id = {record["id"]: record for record in matching}
                self.assertEqual(len(records_by_id), len(matching))
                publishers = {
                    record["publisher"]
                    for record in records_by_id.values()
                }
                publishers_by_period[period_name] = publishers
                self.assertEqual(period["record_count"], len(records_by_id))
                self.assertEqual(period["publisher_count"], len(publishers))
            current = scope["current_period"]
            prior = scope["prior_period"]
            current_publishers = publishers_by_period["current_period"]
            prior_publishers = publishers_by_period["prior_period"]
            common = len(current_publishers & prior_publishers)
            publisher_union = len(current_publishers | prior_publishers)
            round_ratio = lambda value: int(value * 1000 + 0.5) / 1000
            round_signed = lambda value: (
                int(value * 1000 + 0.5) / 1000
                if value >= 0
                else -int(-value * 1000 + 0.5) / 1000
            )
            overlap = round_ratio(common / publisher_union) if publisher_union else 0.0
            record_ratio = (
                round_ratio(
                    max(current["record_count"], prior["record_count"])
                    / min(current["record_count"], prior["record_count"])
                )
                if current["record_count"] and prior["record_count"]
                else None
            )
            quality = scope["comparison_quality"]
            self.assertEqual(quality["current_record_count"], current["record_count"])
            self.assertEqual(quality["prior_record_count"], prior["record_count"])
            self.assertEqual(quality["current_publisher_count"], len(current_publishers))
            self.assertEqual(quality["prior_publisher_count"], len(prior_publishers))
            self.assertEqual(quality["common_publisher_count"], common)
            self.assertEqual(quality["publisher_union_count"], publisher_union)
            self.assertEqual(quality["publisher_overlap_ratio"], overlap)
            self.assertEqual(quality["record_count_ratio"], record_ratio)
            thresholds = quality["thresholds"]
            if (
                current["record_count"] < thresholds["minimum_period_records"]
                or prior["record_count"] < thresholds["minimum_period_records"]
                or len(current_publishers) < thresholds["minimum_period_publishers"]
                or len(prior_publishers) < thresholds["minimum_period_publishers"]
                or common < thresholds["minimum_common_publishers"]
            ):
                expected_quality = ("not_comparable", "insufficient_data")
            elif (
                overlap < thresholds["minimum_publisher_overlap_ratio"]
                or record_ratio is None
                or record_ratio > thresholds["maximum_record_count_ratio"]
            ):
                expected_quality = ("not_comparable", "publisher_panel_changed")
            else:
                expected_quality = ("comparable", "comparable")
            self.assertEqual(
                (quality["status"], quality["reason"]),
                expected_quality,
            )
            self.assertEqual(
                {row["candidate_id"] for row in scope["main"]},
                set(active_field["main"]),
            )
            self.assertEqual(
                {row["candidate_id"] for row in scope["secondary"]},
                set(active_field["secondary"]),
            )
            rows = scope["main"] + scope["secondary"]
            self.assertFalse(
                set(complete_field["hidden"])
                & {row["candidate_id"] for row in rows}
            )
            for row in rows:
                expected_current = (
                    round_ratio(row["current_record_count"] / current["record_count"])
                    if current["record_count"]
                    else None
                )
                expected_prior = (
                    round_ratio(row["prior_record_count"] / prior["record_count"])
                    if prior["record_count"]
                    else None
                )
                self.assertEqual(row["current_share"], expected_current)
                self.assertEqual(row["prior_share"], expected_prior)
                expected_change = (
                    round_signed(expected_current - expected_prior)
                    if quality["status"] == "comparable"
                    and expected_current is not None
                    and expected_prior is not None
                    else None
                )
                self.assertEqual(row["share_change"], expected_change)

    def test_active_projection_structural_mutations_fail(self):
        mutations = []
        count = self.candidate_payload()
        count["active_field_visibility"]["primary"]["current_period"]["record_count"] += 1
        mutations.append(count)
        publishers = self.candidate_payload()
        publishers["active_field_visibility"]["general"]["prior_period"]["publisher_count"] += 1
        mutations.append(publishers)
        hidden = self.candidate_payload()
        hidden["active_field_visibility"]["primary"]["main"][0]["candidate_id"] = "sebastien-lecornu"
        mutations.append(hidden)
        tier = self.candidate_payload()
        tier["active_field_visibility"]["primary"]["secondary"][0]["display_tier"] = "main"
        mutations.append(tier)
        share = self.candidate_payload()
        share["active_field_visibility"]["general"]["main"][0]["current_share"] = 0.999
        mutations.append(share)
        ordering = self.candidate_payload()
        ordering["active_field_visibility"]["primary"]["main"].reverse()
        mutations.append(ordering)
        quality = self.candidate_payload()
        current_reason = quality["active_field_visibility"]["primary"]["comparison_quality"]["reason"]
        quality["active_field_visibility"]["primary"]["comparison_quality"]["reason"] = (
            "publisher_panel_changed"
            if current_reason == "comparable"
            else "comparable"
        )
        mutations.append(quality)
        for payload in mutations:
            with self.subTest(mutation=mutations.index(payload)):
                write_json(self.root, "candidate_signals.json", payload)
                with self.assertRaises(manifest_builder.ManifestError):
                    self.build()
                write_json(self.root, "candidate_signals.json", candidate_signals_payload())

    def test_record_level_denominator_mismatch_fails(self):
        news_path = self.root / "news_wire.json"
        news = json.loads(news_path.read_text(encoding="utf-8"))
        active_names = {
            candidate["candidate_name"]
            for candidate in self.candidate_payload()["candidates"]
            if candidate["candidacy"]["active_field_eligible"]
        }
        removed = next(
            record for record in news["candidate_watch"]
            if record["coverage_scope"] in {"election", "campaign"}
            and record["published_at"][:10] >= "2026-07-25"
            and active_names & set(record["candidates"])
        )
        news["candidate_watch"].remove(removed)
        write_json(self.root, "news_wire.json", news)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "does not match news evidence",
        ):
            self.build()

    def test_valid_active_projection_change_changes_snapshot_id(self):
        first = self.build()["snapshot_id"]
        news_path = self.root / "news_wire.json"
        news = json.loads(news_path.read_text(encoding="utf-8"))
        payload = self.candidate_payload()
        active_names = {
            candidate["candidate_name"]
            for candidate in payload["candidates"]
            if candidate["candidacy"]["active_field_eligible"]
        }
        removed = next(
            record for record in news["candidate_watch"]
            if record["coverage_scope"] == "general"
            and "2026-07-25" <= record["published_at"][:10] <= "2026-07-31"
            and active_names & set(record["candidates"])
        )
        news["candidate_watch"].remove(removed)
        registry = json.loads(
            (self.root / "candidate_candidacy_status.json").read_text(encoding="utf-8")
        )
        payload["active_field_visibility"] = (
            manifest_builder.derive_active_field_visibility(
                news,
                manifest_builder.project_active_monitoring_field(registry),
                registry,
            )
        )
        write_json(self.root, "news_wire.json", news)
        write_json(self.root, "candidate_signals.json", payload)
        self.assertNotEqual(first, self.build()["snapshot_id"])

    def test_missing_candidate_signals_fails(self):
        (self.root / "candidate_signals.json").unlink()
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate_signals.json is missing",
        ):
            self.build()

    def test_malformed_candidate_signals_json_fails(self):
        (self.root / "candidate_signals.json").write_text(
            "{not json",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "malformed JSON",
        ):
            self.build()

    def test_malformed_candidate_signals_structure_fails(self):
        payload = self.candidate_payload()
        payload["visibility"] = []
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaises(manifest_builder.ManifestError):
            self.build()

    def test_duplicate_candidate_ids_fail(self):
        payload = self.candidate_payload()
        payload["candidates"][1]["candidate_id"] = (
            payload["candidates"][0]["candidate_id"]
        )
        payload["candidates"][1]["candidate_name"] = (
            payload["candidates"][0]["candidate_name"]
        )
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate IDs must be unique",
        ):
            self.build()

    def test_candidate_count_mismatch_fails(self):
        payload = self.candidate_payload()
        payload["candidate_universe"]["count"] = 3
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate_universe.count does not match candidates",
        ):
            self.build()

    def test_invalid_candidate_evidence_date_fails(self):
        payload = self.candidate_payload()
        payload["evidence_dates"]["news"] = "2026-02-30"
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "evidence_dates.news must be an ISO calendar date",
        ):
            self.build()

    def test_candidate_evidence_date_uses_latest_non_null_date(self):
        payload = self.candidate_payload()
        payload["evidence_dates"] = {
            "polling": "2026-07-20",
            "news": "2026-07-22",
            "scrutiny": "2026-07-21",
        }
        write_json(self.root, "candidate_signals.json", payload)
        self.assertEqual(
            self.build()["lanes"]["candidate_signals"]["data_as_of"],
            "2026-07-22",
        )

    def test_null_scrutiny_evidence_date_is_valid(self):
        payload = self.candidate_payload()
        payload["evidence_dates"]["scrutiny"] = None
        write_json(self.root, "candidate_signals.json", payload)
        lane = self.build()["lanes"]["candidate_signals"]
        self.assertTrue(lane["valid"])
        expected_data_as_of = max(
            value
            for value in payload["evidence_dates"].values()
            if value is not None
        )
        self.assertEqual(lane["data_as_of"], expected_data_as_of)
        self.assertEqual(lane["warnings"], [])

    def test_candidate_signals_change_changes_snapshot_id(self):
        first = self.build()["snapshot_id"]
        payload = self.candidate_payload()
        payload["candidate_universe"]["rule"] = "Changed fixture rule"
        write_json(self.root, "candidate_signals.json", payload)
        self.assertNotEqual(first, self.build()["snapshot_id"])

    def test_valid_featured_poll_board_is_accepted(self):
        payload = self.candidate_payload()
        self.assertEqual(
            manifest_builder._validate_candidate_signals_public(payload),
            len(payload["candidates"]),
        )

    def test_missing_featured_poll_board_fails(self):
        payload = self.candidate_payload()
        del payload["featured_poll_board"]
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "invalid structure",
        ):
            self.build()

    def test_unknown_candidate_signals_top_level_key_still_fails(self):
        payload = self.candidate_payload()
        payload["unknown"] = True
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "invalid structure",
        ):
            self.build()

    def test_malformed_featured_board_counts_fail(self):
        payload = self.candidate_payload()
        payload["featured_poll_board"]["omitted_candidate_count"] += 1
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "omitted count",
        ):
            self.build()

    def test_duplicate_featured_board_candidate_ids_fail(self):
        payload = self.candidate_payload()
        payload["featured_poll_board"]["candidates"][1][
            "candidate_id"
        ] = payload["featured_poll_board"]["candidates"][0][
            "candidate_id"
        ]
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate IDs must be unique",
        ):
            self.build()

    def test_unknown_featured_board_candidate_id_fails(self):
        payload = self.candidate_payload()
        payload["featured_poll_board"]["candidates"][0][
            "candidate_id"
        ] = "unknown"
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "candidate_id is not in main candidates",
        ):
            self.build()

    def test_mismatched_featured_board_candidate_name_fails(self):
        payload = self.candidate_payload()
        payload["featured_poll_board"]["candidates"][0][
            "candidate_name"
        ] = "Candidate B"
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "name is not canonical",
        ):
            self.build()

    def test_noncontiguous_featured_board_positions_fail(self):
        payload = self.candidate_payload()
        payload["featured_poll_board"]["candidates"][-1][
            "display_position"
        ] += 1
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "not contiguous",
        ):
            self.build()

    def test_incorrect_featured_board_score_order_fails(self):
        payload = self.candidate_payload()
        rows = payload["featured_poll_board"]["candidates"]
        rows[0], rows[1] = rows[1], rows[0]
        for position, row in enumerate(rows, start=1):
            row["display_position"] = position
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "not correctly ordered",
        ):
            self.build()

    def test_invalid_featured_board_source_url_fails(self):
        payload = self.candidate_payload()
        payload["featured_poll_board"]["source_urls"] = ["relative/path"]
        write_json(self.root, "candidate_signals.json", payload)
        with self.assertRaisesRegex(
            manifest_builder.ManifestError,
            "featured_poll_board.source_urls is invalid",
        ):
            self.build()

    def test_generated_candidate_signals_passes_public_validation(self):
        payload = json.loads(
            (ROOT / "candidate_signals.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest_builder._validate_candidate_signals_public(payload),
            len(payload["candidates"]),
        )

    def test_missing_lane_completes_with_warning(self):
        (self.root / "news_wire.json").unlink()
        manifest = self.build()
        lane = manifest["lanes"]["news"]
        self.assertFalse(lane["available"])
        self.assertFalse(lane["valid"])
        self.assertIsNone(lane["sha256"])
        self.assertEqual(lane["timestamp_status"], "missing")
        self.assertIn("news_wire.json is missing", lane["warnings"])
        self.assertIn("news_wire.json is missing", manifest["warnings"])

    def test_malformed_lane_completes_with_warning(self):
        (self.root / "claims_under_scrutiny.json").write_text(
            "{not json",
            encoding="utf-8",
        )
        manifest = self.build()
        lane = manifest["lanes"]["claims"]
        self.assertTrue(lane["available"])
        self.assertFalse(lane["valid"])
        self.assertRegex(lane["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(lane["timestamp_status"], "invalid")
        self.assertTrue(
            any("malformed JSON" in warning for warning in lane["warnings"])
        )

    def test_poll_timestamp_is_unknown(self):
        lane = self.build()["lanes"]["polls"]
        self.assertEqual(lane["timestamp_status"], "unknown")
        self.assertNotIn("generated_at", lane)
        self.assertNotIn("last_success_at", lane)

    def test_no_cross_lane_timestamp_inference(self):
        manifest = self.build()
        recent_check = manifest["lanes"]["recent_changes"]["last_success_at"]
        self.assertEqual(recent_check, "2026-07-25T08:04:00Z")
        self.assertNotIn(recent_check, manifest["lanes"]["polls"].values())
        self.assertEqual(
            manifest["lanes"]["polls"]["timestamp_status"],
            "unknown",
        )

    def test_poll_data_as_of_uses_latest_valid_fieldwork_end(self):
        self.assertEqual(
            self.build()["lanes"]["polls"]["data_as_of"],
            "2026-07-10",
        )

    def test_runoff_data_as_of_uses_latest_valid_fieldwork_end(self):
        self.assertEqual(
            self.build()["lanes"]["runoff"]["data_as_of"],
            "2026-07-08",
        )

    def test_claim_data_as_of_uses_latest_valid_review_date(self):
        self.assertEqual(
            self.build()["lanes"]["claims"]["data_as_of"],
            "2026-07-17",
        )

    def test_source_network_metrics_remain_separate(self):
        network = self.build()["source_network"]
        self.assertEqual(
            network,
            {
                "approved_publisher_domains": 202,
                "configured_media_publishers": 180,
                "configured_routes_or_feeds": 209,
                "routes_due_in_run": 53,
                "successful_due_routes": 52,
                "contributing_publishers_in_retained_period": 86,
                "publishers_represented_in_accepted_election_news": 2,
            },
        )

    def test_source_health_aggregate_remains_operationally_distinct(self):
        manifest = self.build()
        self.assertEqual(
            manifest["source_health"],
            {
                "configured_routes": 4,
                "attempted_routes": 4,
                "successful_routes": 3,
                "failed_routes": 1,
                "repeated_failure_routes": 1,
                "healthy_zero_yield_routes": 1,
                "recovered_routes": 1,
            },
        )
        self.assertEqual(
            manifest["source_network"]["approved_publisher_domains"],
            202,
        )
        self.assertNotIn(
            "approved_publisher_domains",
            manifest["source_health"],
        )

    def test_atomic_output_replaces_the_target_only_at_the_end(self):
        target = self.root / manifest_builder.OUTPUT_NAME
        target.write_text("last good", encoding="utf-8")
        payload = self.build()

        with patch.object(
            manifest_builder.os,
            "replace",
            side_effect=OSError("simulated replace failure"),
        ):
            with self.assertRaises(OSError):
                manifest_builder.atomic_write_json(target, payload)

        self.assertEqual(target.read_text(encoding="utf-8"), "last good")
        self.assertEqual(
            list(self.root.glob(f".{manifest_builder.OUTPUT_NAME}.*.tmp")),
            [],
        )

        manifest_builder.atomic_write_json(target, payload)
        written = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(written["snapshot_id"], payload["snapshot_id"])

    def test_check_does_not_modify_publication_manifest(self):
        target = self.root / manifest_builder.OUTPUT_NAME
        original = '{"sentinel": true}\n'
        target.write_text(original, encoding="utf-8")

        with patch.object(Path, "cwd", return_value=self.root):
            exit_code = manifest_builder.main(
                ["--check", "--published-at", PUBLISHED_AT]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_content_change_changes_snapshot_id(self):
        first = self.build()["snapshot_id"]
        polls = json.loads((self.root / "polls.json").read_text(encoding="utf-8"))
        polls.append({"fieldwork_end": "2026-07-11"})
        write_json(self.root, "polls.json", polls)
        self.assertNotEqual(first, self.build()["snapshot_id"])


if __name__ == "__main__":
    unittest.main()
