from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fetch_source_icons as icons


class DynamicTargetTests(unittest.TestCase):
    def write_json(
        self,
        path: Path,
        payload,
    ) -> None:
        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_surfaced_publishers_resolve_from_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "publisher_policy.json"
            surface = root / "recent_changes.json"

            self.write_json(
                policy,
                {
                    "lesechos.fr": {
                        "name": "Les Echos",
                        "source_type": "media",
                        "tier": "core",
                        "enabled": True,
                    },
                    "liberation.fr": {
                        "name": "Libération",
                        "source_type": "media",
                        "tier": "core",
                        "enabled": True,
                    },
                    "lcp.fr": {
                        "name": "LCP — Actualités",
                        "source_type": "media",
                        "tier": "core",
                        "enabled": True,
                    },
                },
            )

            self.write_json(
                surface,
                {
                    "items": [
                        {
                            "source_icon_key": "Les Echos",
                            "primary_source": {
                                "name": "Les Echos",
                                "url": (
                                    "https://news.google.com/"
                                    "rss/articles/example"
                                ),
                            },
                        },
                        {
                            "source_icon_key": "Libération",
                            "primary_source": {
                                "name": "Libération",
                                "url": (
                                    "https://news.google.com/"
                                    "rss/articles/example-2"
                                ),
                            },
                        },
                        {
                            "source_icon_key": "LCP",
                            "primary_source": {
                                "name": "LCP — Actualités",
                                "url": "https://lcp.fr/actualites/test",
                            },
                        },
                    ]
                },
            )

            targets = icons.dynamic_surface_targets(
                policy_path=policy,
                surface_paths=[surface],
            )

            self.assertEqual(
                {
                    target["name"]
                    for target in targets
                },
                {
                    "Les Echos",
                    "Libération",
                    "LCP — Actualités",
                },
            )

    def test_disabled_and_unknown_publishers_are_not_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "publisher_policy.json"
            surface = root / "recent_changes.json"

            self.write_json(
                policy,
                {
                    "disabled.example": {
                        "name": "Disabled Publisher",
                        "source_type": "media",
                        "tier": "extended",
                        "enabled": False,
                    }
                },
            )

            self.write_json(
                surface,
                {
                    "items": [
                        {
                            "source_icon_key": "Disabled Publisher",
                            "primary_source": {
                                "name": "Disabled Publisher",
                                "url": "https://disabled.example/story",
                            },
                        },
                        {
                            "source_icon_key": "Unknown Publisher",
                            "primary_source": {
                                "name": "Unknown Publisher",
                                "url": "https://unknown.example/story",
                            },
                        },
                    ]
                },
            )

            targets = icons.dynamic_surface_targets(
                policy_path=policy,
                surface_paths=[surface],
            )

            self.assertEqual(targets, [])


class CacheAndFailureTests(unittest.TestCase):
    def create_cached_record(
        self,
        root: Path,
        publisher: str,
    ):
        icon_path = (
            root
            / "assets"
            / "source-icons"
            / f"{icons.slugify(publisher)}.png"
        )
        icon_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        icon_path.write_bytes(b"x" * 64)

        return {
            "publisher": publisher,
            "status": "ok",
            "homepage_url": "https://example.com/",
            "icon_url": "https://example.com/icon.png",
            "path": icon_path.relative_to(root).as_posix(),
            "mime_type": "image/png",
            "retrieved_at": "2026-07-20T00:00:00Z",
            "error": None,
            "entity_type": "publisher",
        }

    def test_valid_cache_causes_no_network_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self.create_cached_record(
                root,
                "Example",
            )

            with patch.object(
                icons,
                "retrieve_source_icon",
            ) as retrieve:
                records = icons.build_icon_records(
                    targets=[
                        {
                            "name": "Example",
                            "feed_url": "https://example.com/feed",
                            "entity_type": "publisher",
                        }
                    ],
                    existing={"Example": record},
                    icons_dir=(
                        root / "assets" / "source-icons"
                    ),
                    repository_root=root,
                    refresh=False,
                    retry_errors=False,
                )

            retrieve.assert_not_called()
            self.assertEqual(records, [record])

    def test_one_failed_publisher_does_not_stop_other_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            icon_dir = root / "assets" / "source-icons"
            icon_dir.mkdir(parents=True)

            def retrieve(**kwargs):
                publisher = kwargs["publisher"]

                if publisher == "Broken":
                    raise RuntimeError("blocked")

                path = icon_dir / "working.png"
                path.write_bytes(b"x" * 64)

                return {
                    "publisher": publisher,
                    "status": "ok",
                    "homepage_url": "https://working.example/",
                    "icon_url": (
                        "https://working.example/icon.png"
                    ),
                    "path": path.relative_to(root).as_posix(),
                    "mime_type": "image/png",
                    "retrieved_at": "2026-07-20T00:00:00Z",
                    "error": None,
                }

            with patch.object(
                icons,
                "retrieve_source_icon",
                side_effect=retrieve,
            ):
                records = icons.build_icon_records(
                    targets=[
                        {
                            "name": "Broken",
                            "feed_url": (
                                "https://broken.example/feed"
                            ),
                            "entity_type": "publisher",
                        },
                        {
                            "name": "Working",
                            "feed_url": (
                                "https://working.example/feed"
                            ),
                            "entity_type": "publisher",
                        },
                    ],
                    existing={},
                    icons_dir=icon_dir,
                    repository_root=root,
                    refresh=False,
                    retry_errors=False,
                )

            statuses = {
                record["publisher"]: record["status"]
                for record in records
            }

            self.assertEqual(statuses["Broken"], "error")
            self.assertEqual(statuses["Working"], "ok")

    def test_inactive_successful_icon_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self.create_cached_record(
                root,
                "Historical Publisher",
            )

            records = icons.build_icon_records(
                targets=[],
                existing={
                    "Historical Publisher": record
                },
                icons_dir=(
                    root / "assets" / "source-icons"
                ),
                repository_root=root,
                refresh=False,
                retry_errors=False,
            )

            self.assertEqual(records, [record])


class ManifestTests(unittest.TestCase):
    def test_timestamp_only_change_does_not_rewrite_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source_icons.json"

            original = {
                "schema_version": 1,
                "generated_at": "2026-07-20T00:00:00Z",
                "method": "method",
                "sources": [
                    {
                        "publisher": "Example",
                        "status": "error",
                        "homepage_url": (
                            "https://example.com/"
                        ),
                        "icon_url": None,
                        "path": None,
                        "mime_type": None,
                        "retrieved_at": (
                            "2026-07-20T00:00:00Z"
                        ),
                        "error": "blocked",
                        "entity_type": "publisher",
                    }
                ],
            }

            path.write_text(
                json.dumps(original, indent=2) + "\n",
                encoding="utf-8",
            )

            replacement = json.loads(
                json.dumps(original)
            )
            replacement["generated_at"] = (
                "2026-07-21T00:00:00Z"
            )
            replacement["sources"][0]["retrieved_at"] = (
                "2026-07-21T00:00:00Z"
            )

            changed = icons.write_manifest_if_changed(
                output_path=path,
                payload=replacement,
            )

            self.assertFalse(changed)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                original,
            )


class WorkflowTests(unittest.TestCase):
    def test_news_workflow_runs_and_commits_dynamic_icons(self):
        workflow = Path(
            ".github/workflows/update-news-wire.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "test_fetch_source_icons.py",
            workflow,
        )
        self.assertIn(
            "Update dynamic source icons",
            workflow,
        )
        self.assertIn(
            "--surface-data /tmp/recent_changes.json",
            workflow,
        )
        self.assertIn(
            "source_icons.json",
            workflow,
        )
        self.assertIn(
            "assets/source-icons",
            workflow,
        )
        self.assertIn(
            "steps.icons.outputs.changed == 'true'",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
