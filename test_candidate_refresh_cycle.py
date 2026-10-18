"""Offline future publication transactions; every write is in an isolated copy."""
from datetime import date, datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from lxml import html
import build_candidate_reference as reference
import build_publication_manifest as manifest
import build_route_registry as routes
import build_search_entrypoints as search
import build_sitemaps as sitemaps
from build_candidate_signals import atomic_write
from candidate_history import HistoryError, encode, instant, iso

ROOT = Path(__file__).resolve().parent
PROVIDERS = ("polymarket", "youtube", "bluesky")
MAPPINGS = dict(polymarket="polymarket_candidate_markets.json",
                youtube="youtube_candidate_channels.json", bluesky="bluesky_candidate_accounts.json")


class Profiles:
    """Deterministic public API responses for the pinned production identities."""
    def __init__(self, provider, mapping, day, fail=False):
        self.provider, self.day, self.fail = provider, day, fail
        self.requests = {part: 0 for part in ("channels", "playlistItems", "videos")}
        self.configs = mapping["accounts" if provider == "bluesky" else "channels"]

    def assert_secret_absent(self, value):
        assert "YOUTUBE_API_KEY" not in json.dumps(value)

    def get(self, endpoint, **params):
        if self.fail:
            raise ValueError("injected collection failure")
        if self.provider == "youtube":
            self.requests[endpoint] += 1
            if endpoint != "channels":
                return {"items": []}
            return {"items": [{"id": cid, "snippet": {"title": "Synthetic official channel"},
                "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}},
                "statistics": {"hiddenSubscriberCount": False,
                    "subscriberCount": str(100000 + self.day * 1000),
                    "viewCount": "2000000", "videoCount": "0"}}
                for cid in params["id"].split(",")]}
        if endpoint.endswith("resolveHandle"):
            cid = params["handle"].removesuffix(".bsky.social")
            return {"did": next(c["did"] for c in self.configs if c["candidate_id"] == cid)}
        self.requests[endpoint] = self.requests.get(endpoint, 0) + 1
        return {"profiles": [{"did": c["did"], "handle": c["candidate_id"] + ".bsky.social",
            "displayName": "Synthetic official account", "followersCount": 20000 + self.day * 100,
            "followsCount": 10, "postsCount": 100, "labels": []}
            for c in self.configs if c["did"] in params["actors"]]}


class CandidateRefreshCycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        # Copy tracked files only: never recursively copy a temporary child of ROOT.
        names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
        for name in filter(None, names):
            source, target = ROOT / name, self.root / name
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        # Newly added test files are not staged during development.
        for name in ("test_candidate_refresh_cycle.py",):
            shutil.copyfile(ROOT / name, self.root / name)
        self.mapping = {p: self.read(MAPPINGS[p]) for p in PROVIDERS}
        self.original = {p: self.read(f"candidate_{p}_history.json") for p in PROVIDERS}
        # Attention/news may have refreshed after the provider snapshots. The
        # simulated future must follow all current publication clocks.
        clocks = []
        for name in reference.SOURCE_FILES.values():
            payload = self.read(name)
            if not isinstance(payload, dict):
                continue
            for key in ("generated_at", "observed_at", "published_at"):
                value = payload.get(key)
                if isinstance(value, str) and "T" in value:
                    clocks.append(instant(value))
        latest = max(clocks)
        self.start = datetime.combine(latest.date() + timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=12)
        self.trace = []
        self.observations = {p: set() for p in PROVIDERS}
        self.network = mock.patch("urllib.request.urlopen", side_effect=AssertionError("live API forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def read(self, name):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def collect_and_append(self, day, *, fail_collection=False, fail_history=False):
        self.trace.append("collection")
        stamp = iso(self.start + timedelta(days=day - 1))
        event = json.loads((ROOT / "test_fixtures/polymarket_event.json").read_text(encoding="utf-8"))
        template = event["markets"][0]
        event["markets"] = []
        for index, config in enumerate(self.mapping["polymarket"]["markets"]):
            price = .4 + day / 1000
            row = dict(template, id=config["market_id"], slug=config["market_slug"],
                groupItemTitle=config["group_item_title"], version="v1", active=True, closed=False,
                archived=False, acceptingOrders=True, outcomes='["Yes","No"]',
                clobTokenIds=json.dumps([config["outcome_id"], str(index + 1)]),
                outcomePrices=json.dumps([str(price), str(1 - price)]), updatedAt=stamp)
            # Reviewed mapping coverage must not mean every market is observed.
            if config["candidate_id"] == "gabriel-attal":
                row.update(active=False, closed=True, acceptingOrders=False)
            event["markets"].append(row)
        event["updatedAt"] = stamp
        import build_candidate_polymarket as poly
        poly.collect(self.root / "candidate_polymarket.json", mapping_path=self.root / MAPPINGS["polymarket"],
            registry_path=self.root / "candidate_candidacy_status.json", fetch=lambda: event, observed_at=stamp)
        for offset, provider in enumerate(("youtube", "bluesky"), 1):
            builder = importlib.import_module("build_candidate_" + provider)
            builder.collect(self.root / f"candidate_{provider}.json", mapping_path=self.root / MAPPINGS[provider],
                registry_path=self.root / "candidate_candidacy_status.json",
                client=Profiles(provider, self.mapping[provider], day, fail_collection and provider == "youtube"),
                observed_at=iso(instant(stamp) + timedelta(minutes=offset)))
        for provider in PROVIDERS:
            snapshot = self.read(f"candidate_{provider}.json")
            field = {"polymarket": "implied_probability", "youtube": "subscriber_count",
                     "bluesky": "followers_count"}[provider]
            for row in snapshot["candidates"]:
                if row["status"] == "observed" and row[field] is not None:
                    self.observations[provider].add((row["candidate_id"], snapshot["observed_at"], row[field]))
        self.trace.append("histories")
        for provider in PROVIDERS:
            builder = importlib.import_module("build_candidate_" + provider + "_history")
            kwargs = dict(snapshot_path=self.root / f"candidate_{provider}.json",
                mapping_path=self.root / MAPPINGS[provider], registry_path=self.root / "candidate_candidacy_status.json")
            if provider == "polymarket":
                def fetch(token, start, end):
                    self.assertIn(token, {c["outcome_id"] for c in self.mapping["polymarket"]["markets"]})
                    return {"history": []}  # No invented historical source samples.
                builder.collect(self.root / f"candidate_{provider}_history.json", mode="incremental", fetch=fetch, **kwargs)
            else:
                with mock.patch.object(builder, "build_history", side_effect=HistoryError("injected history validation failure")) if fail_history and provider == "bluesky" else mock.patch.object(builder, "build_history", wraps=builder.build_history):
                    builder.update(self.root / f"candidate_{provider}_history.json", **kwargs)
        return iso(instant(stamp) + timedelta(hours=1))

    def refresh_attention(self, stamp):
        # An independent Attention refresh may precede candidate publication.
        from build_candidate_attention import calculate_candidate_metrics, interpretation_flag
        from candidate_attention_contract import validate_candidate_attention
        attention = self.read("candidate_attention.json")
        shift = instant(stamp).date() - instant(attention["generated_at"]).date()
        for key in ("start_date", "end_date", "data_as_of"):
            attention["period"][key] = (date.fromisoformat(attention["period"][key]) + shift).isoformat()
        attention["generated_at"] = stamp
        for row in attention["candidates"]:
            if row["evidence_state"] == "observed":
                for day in row["daily_series"]:
                    day["date"] = (date.fromisoformat(day["date"]) + shift).isoformat()
                    day["views"] += 17
                metrics = calculate_candidate_metrics(row["daily_series"],
                    data_as_of=date.fromisoformat(attention["period"]["data_as_of"]))
                row.update(metrics, interpretation_flag=interpretation_flag(metrics))
        validate_candidate_attention(attention)
        atomic_write(self.root / "candidate_attention.json", encode(attention))

    def rebuild(self, published):
        self.trace.append("rebuild")
        # Snapshot/history agreement is required before creating the manifest.
        reference.load_signal_histories(self.root)
        payload = manifest.build_manifest(self.root, published_at=published)
        manifest.atomic_write_json(self.root / "publication_manifest.json", payload)
        civil = instant(published).date()
        with mock.patch.object(reference, "_event_reference_date", return_value=civil):
            artifacts = reference.build_all_active_artifacts(reference.load_sources(self.root), self.root)
        for relative, content in artifacts.items():
            atomic_write(self.root / relative, content)
        args = dict(root=self.root, poll_manifest_path=self.root / "poll_pages_manifest.json",
            candidate_registry_path=self.root / "candidate_candidacy_status.json",
            issue_manifest_path=self.root / "issue_pages_manifest.json", agenda_manifest_path=self.root / "agenda_pages_manifest.json")
        for phase in (0, 1):
            registry = routes.build_registry(**args, existing_registry_path=self.root / "route_registry.json", effective_date=civil.isoformat())
            atomic_write(self.root / "route_registry.json", routes.serialize_registry(registry))
            if phase == 0:
                search.generate_entrypoints(source_path=self.root / "index.html", english_output_path=self.root / "en/index.html",
                    candidate_signals_path=self.root / "candidate_signals.json", recent_changes_path=self.root / "recent_changes.json")
        sitemaps.build_from_paths(self.root / "route_registry.json", output_root=self.root)
        self.trace.append("post-build validation")
        self.assertEqual(routes.check_registry(**args, registry_path=self.root / "route_registry.json"), [])
        self.assertEqual(sitemaps.check_from_paths(self.root / "route_registry.json", output_root=self.root), [])
        manifest.validate_manifest(self.read("publication_manifest.json"))
        self.assertEqual(manifest.build_manifest(self.root, published_at=published), self.read("publication_manifest.json"))
        search.generate_entrypoints(source_path=self.root / "index.html", english_output_path=self.root / "en/index.html",
            candidate_signals_path=self.root / "candidate_signals.json", recent_changes_path=self.root / "recent_changes.json", check=True)
        with mock.patch.object(reference, "_event_reference_date", return_value=civil):
            for path, content in reference.build_all_active_artifacts(reference.load_sources(self.root), self.root).items():
                self.assertTrue(reference._newline_equivalent((self.root / path).read_bytes(), content))

    def cycle(self, day, publish, **failures):
        published = self.collect_and_append(day, **failures)
        self.rebuild(published)
        self.trace.append("publication")
        publish()

    def test_two_future_publications_with_mature_histories_and_independent_attention(self):
        for day in range(1, 8):  # Deterministic offline fixture observations.
            self.collect_and_append(day)
            if day == 1:
                import candidate_public_signal_trend as trend
                histories = trend.load_histories(self.root)
                for provider in ("youtube", "bluesky"):
                    snapshot = self.read(f"candidate_{provider}.json")
                    row = next(r for r in snapshot["candidates"] if r["candidate_id"] == "francois-ruffin")
                    current = dict(row, observed_at=snapshot["observed_at"])
                    rendered = trend.render_movement(provider, "francois-ruffin", current, histories, "en")
                    baseline = trend.PROVIDERS[provider][0].derive_delta(histories[provider]["francois-ruffin"], 7)
                    if baseline is None:
                        self.assertEqual(rendered, "")
                    else:
                        self.assertIn('class="candidate-public-signal-change"', rendered)
        self.trace.clear()
        publish = mock.Mock()
        self.cycle(8, publish)
        first_manifest = self.read("publication_manifest.json")
        self.refresh_attention(iso(self.start + timedelta(days=8, hours=1)))
        self.cycle(9, publish)
        self.assertEqual(publish.call_count, 2)
        self.assertNotEqual(first_manifest["snapshot_id"], self.read("publication_manifest.json")["snapshot_id"])
        self.assertEqual(self.trace, ["collection", "histories", "rebuild", "post-build validation", "publication"] * 2)
        for provider in PROVIDERS:
            history = self.read(f"candidate_{provider}_history.json")
            snapshot = self.read(f"candidate_{provider}.json")
            self.assertEqual(history["observed_at"], snapshot["observed_at"])
            cutoff = instant(history["observed_at"]).date() - timedelta(days=89)
            original = {r["candidate_id"]: r for r in self.original[provider]["candidates"]}
            identity = {"polymarket": "yes_token_id", "youtube": "channel_id", "bluesky": "did"}[provider]
            for row in history["candidates"]:
                self.assertEqual(row[identity], original[row["candidate_id"]][identity])
                self.assertLessEqual(len(row["points"]), 90)
                self.assertTrue(all(instant(p["observed_at"]).date() >= cutoff for p in row["points"]))
                retained = [p for p in original[row["candidate_id"]]["points"] if instant(p["observed_at"]).date() >= cutoff]
                self.assertEqual(row["points"][:len(retained)], retained)
                field = {"polymarket": "implied_probability", "youtube": "subscriber_count",
                         "bluesky": "followers_count"}[provider]
                old = {(row["candidate_id"], p["observed_at"], p[field])
                       for p in original[row["candidate_id"]]["points"]}
                self.assertTrue(all((row["candidate_id"], p["observed_at"], p[field]) in old | self.observations[provider]
                                    for p in row["points"]))
        for lang in ("fr", "en"):
            prefix = "en/" if lang == "en" else ""
            document = html.fromstring((self.root / f"{prefix}candidates/francois-ruffin/index.html").read_bytes())
            projected = self.read("candidates/francois-ruffin/data.json")
            for provider in PROVIDERS:
                card = document.xpath(f'.//article[@data-provider="{provider}"]')[0]
                self.assertEqual(len(card.xpath('.//p[@class="candidate-public-signal-change"]')), 1)
                self.assertEqual(len(card.xpath('.//svg')), 1)
                field = {"polymarket": "implied_probability", "youtube": "subscriber_count", "bluesky": "followers_count"}[provider]
                current = projected[provider][field]
                expected = ((f"{current * 100:.1f}".replace(".", ",") + "\u00a0%") if lang == "fr" else f"{current * 100:.1f}%") if provider == "polymarket" else reference._public_signal_number(current, lang)
                self.assertEqual(card.xpath('.//p[@class="candidate-public-signal-value"]')[0].text_content(), expected)
            self.assertNotIn('data-score=', html.tostring(document).decode())
        # Run the repaired real-artifact tests against this refreshed copy.
        script = """import unittest
from unittest.mock import patch
suite = unittest.defaultTestLoader.loadTestsFromNames([
 'test_candidate_public_signals',
 'test_candidate_youtube.YouTubeTests.test_candidate_builder_projection_and_public_signal_card',
 'test_candidate_youtube.TaskOnePreservationTests.test_representative_polymarket_values_and_html',
 'test_candidate_bluesky.BlueskyPublicationTests.test_candidate_projection_and_public_signal_card'])
with patch('urllib.request.urlopen', side_effect=AssertionError('live API forbidden')):
 result = unittest.TextTestRunner().run(suite)
raise SystemExit(not result.wasSuccessful())
"""
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_failed_transaction(self, **failure):
        publish = mock.Mock()
        paths = [self.root / name for name in ("publication_manifest.json", "route_registry.json",
            "index.html", "en/index.html", "sitemap.xml", "sitemap-candidates.xml",
            "sitemap-core.xml", "sitemap-polls.xml")]
        paths += [p for prefix in ("candidates", "en/candidates")
                  for p in (self.root / prefix).rglob("*") if p.is_file()]
        before = [p.read_bytes() for p in paths]
        history = self.root / "candidate_bluesky_history.json"
        previous_history = history.read_bytes()
        youtube = self.root / "candidate_youtube.json"
        previous_youtube = youtube.read_bytes()
        with self.assertRaises((ValueError, OSError)):
            self.cycle(1, publish, **failure)
        publish.assert_not_called()
        self.assertNotIn("rebuild", self.trace)
        self.assertNotIn("post-build validation", self.trace)
        self.assertEqual([p.read_bytes() for p in paths], before)
        self.assertEqual(history.read_bytes(), previous_history)
        if failure.get("fail_collection"):
            self.assertEqual(youtube.read_bytes(), previous_youtube)

    def test_collection_failure_retains_previous_snapshot_and_cannot_publish(self):
        self.assert_failed_transaction(fail_collection=True)

    def test_history_validation_failure_retains_previous_history_and_cannot_publish(self):
        self.assert_failed_transaction(fail_history=True)


if __name__ == "__main__":
    unittest.main()
