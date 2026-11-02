"""Keep dashboard production independent of the retired delivery subsystem."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
RETIRED_MODULES = {
    "candidate_media_pulse", "daily_plan", "daily_queue", "newsroom_products",
    "planner_readiness", "queue_metadata", "radar_media", "signal_engine",
    "social_publish", "weekly_flagship", "weekly_flagship_catchup",
}


class PublisherRetirementTests(unittest.TestCase):
    def test_production_workflows_have_no_x_delivery_integration(self):
        self.assertFalse((ROOT / ".github/workflows/publish-x-fr.yml").exists())
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                for token in ("BUFFER_API_KEY", "BUFFER_ORGANIZATION_ID",
                              "BUFFER_X_CHANNEL_ID", "FR27_SOCIAL_ENABLED",
                              "FR27_BUFFER_SCHEDULING_ENABLED", "social-assets"):
                    self.assertNotIn(token, source)
                for name in RETIRED_MODULES:
                    self.assertNotIn("social/" + name + ".py", source)

    def test_production_python_has_no_retired_publisher_imports(self):
        paths = [p for p in ROOT.glob("*.py") if not p.name.startswith("test_")]
        paths.extend((ROOT / "social").glob("*.py"))
        paths.extend((ROOT / "tools").rglob("*.py"))
        for path in paths:
            if "node_modules" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                    if node.module == "social":
                        names.extend(alias.name for alias in node.names)
                for name in names:
                    with self.subTest(path=path.relative_to(ROOT), module=name):
                        self.assertTrue(RETIRED_MODULES.isdisjoint(name.split(".")))


if __name__ == "__main__":
    unittest.main()
