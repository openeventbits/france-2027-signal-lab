import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "update-news-wire.yml"


class NewsWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_hourly_schedule_and_explicit_registry(self):
        self.assertIn('cron: "23 * * * *"', self.text)
        self.assertIn("workflow_dispatch:", self.text)
        fetch_start = self.text.index("python fetch_news_wire.py")
        fetch_end = self.text.index("python generate_recent_changes.py", fetch_start)
        fetch = self.text[fetch_start:fetch_end]
        self.assertIn(
            "--candidacy-status candidate_candidacy_status.json",
            fetch,
        )
        self.assertIn("--polls polls.json", fetch)

    def test_registry_is_not_published_by_news(self):
        commit = self.text[self.text.index("git add --"):]
        for line in commit.splitlines():
            if "git add" in line:
                self.assertNotIn("candidate_candidacy_status.json", line)


if __name__ == "__main__":
    unittest.main()
