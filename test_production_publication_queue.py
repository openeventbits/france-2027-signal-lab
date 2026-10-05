"""Discover production writers and enforce the workflow-level waiting queue.

This intentionally parses only scalar concurrency mappings. Unsupported production
concurrency syntax fails closed rather than silently dropping a participating file.
"""
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GROUP = "production-data-update"
MINIMUM_MEMBERS = {
    "publish-candidate-family.yml", "publish-issue-family.yml",
    "publish-agenda-family.yml", "publish-dashboard.yml", "refresh-og-cover.yml",
    "update-candidate-attention.yml", "update-candidate-universe.yml",
    "update-claims-under-scrutiny.yml", "update-news-wire.yml", "update-polls.yml",
}


def scalar(value):
    value = re.sub(r"\s+#.*$", "", value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def production_concurrency(text):
    lines = text.splitlines()
    found = []
    for index, line in enumerate(lines):
        match = re.fullmatch(r"( *)concurrency:\s*(.*?)\s*", line)
        if not match:
            continue
        indent, tail = len(match[1]), match[2]
        if tail and not tail.startswith("#"):
            if GROUP in tail:
                raise AssertionError("production concurrency must use a scalar block mapping")
            continue
        fields = {}
        field_indent = None
        for child in lines[index + 1:]:
            if not child.strip() or child.lstrip().startswith("#"):
                continue
            depth = len(child) - len(child.lstrip(" "))
            if depth <= indent:
                break
            if field_indent is None:
                field_indent = depth
            if depth != field_indent:
                continue
            field = re.fullmatch(r"\s*([\w-]+):\s*(.*?)\s*", child)
            if field:
                key, value = field.groups()
                if key in fields:
                    raise AssertionError(f"duplicate concurrency key: {key}")
                fields[key] = scalar(value)
        if fields.get("group") == GROUP:
            if indent != 0:
                raise AssertionError("production serialization must be workflow-level")
            if fields != {"group": GROUP, "cancel-in-progress": "false", "queue": "max"}:
                raise AssertionError(f"invalid production queue: {fields}")
            found.append(fields)
    if len(found) > 1:
        raise AssertionError("duplicate workflow production concurrency")
    if not found and re.search(
        r"(?m)^\s*['\"]?group['\"]?:\s*['\"]?production-data-update['\"]?\s*(?:#.*)?$", text
    ):
        raise AssertionError("production group declaration was not parsed as workflow concurrency")
    return found


def discover_production_workflows(directory):
    members = {}
    for path in sorted(directory.glob("*.yml")):
        contracts = production_concurrency(path.read_text(encoding="utf-8"))
        if contracts:
            members[path.name] = contracts[0]
    return members


class ProductionPublicationQueueTests(unittest.TestCase):
    def test_every_discovered_production_writer_uses_max_queue(self):
        members = discover_production_workflows(ROOT / ".github/workflows")
        self.assertTrue(MINIMUM_MEMBERS <= members.keys(), MINIMUM_MEMBERS - members.keys())

    def test_future_member_is_discovered_without_a_filename_list(self):
        text = "concurrency:\n  group: production-data-update\n  cancel-in-progress: false\n  queue: max\n"
        self.assertEqual(len(production_concurrency(text)), 1)
        with tempfile.TemporaryDirectory() as directory:
            future = Path(directory) / "future-production-writer.yml"
            future.write_text(text, encoding="utf-8")
            self.assertEqual(set(discover_production_workflows(Path(directory))), {future.name})
            future.write_text(text.replace("  queue: max\n", ""), encoding="utf-8")
            with self.assertRaises(AssertionError):
                discover_production_workflows(Path(directory))
        for broken in (
            text.replace("  queue: max\n", ""),
            text.replace("cancel-in-progress: false", "cancel-in-progress: true"),
            text.replace("queue: max", "queue: single"),
            text + "  queue: single\n",
            "  " + text.replace("\n", "\n  ").rstrip() + "\n",
            "concurrency: {group: production-data-update, queue: max}\n",
            text.replace("concurrency:", '"concurrency":'),
        ):
            with self.subTest(text=broken), self.assertRaises(AssertionError):
                production_concurrency(broken)

    def test_quotes_comments_and_key_order_are_supported(self):
        text = '''# concurrency is workflow-level
concurrency: # production
  queue: 'max' # retain pending runs
  cancel-in-progress: false
  group: "production-data-update"
jobs:
  test:
    runs-on: ubuntu-latest
'''
        self.assertEqual(len(production_concurrency(text)), 1)
        self.assertEqual(production_concurrency(text.replace(GROUP, "unrelated")), [])


if __name__ == "__main__":
    unittest.main()
