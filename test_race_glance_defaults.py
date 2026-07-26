from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"


class RaceGlanceDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = INDEX.read_text(encoding="utf-8")

    def test_packages_are_ranked_after_full_package_build(self):
        self.assertIn(
            "function raceComparableCandidateCount(",
            self.source,
        )
        self.assertIn(
            "function rankRacePollPackages(",
            self.source,
        )
        self.assertIn(
            "return packages;",
            self.source,
        )
        self.assertNotIn(
            "return packages.slice(0, 3);",
            self.source,
        )
        self.assertIn(
            "const pollPackages = rankRacePollPackages(",
            self.source,
        )
        self.assertIn(
            "buildRacePollPackages(validEvents),",
            self.source,
        )
        self.assertIn(
            ").slice(0, 3);",
            self.source,
        )

    def test_newest_date_precedes_comparable_coverage_ranking(self):
        self.assertIn(
            "b.fieldwork_end.localeCompare(a.fieldwork_end)",
            self.source,
        )
        self.assertIn(
            "comparisonCountByPackage.get(b.key) -",
            self.source,
        )
        self.assertIn(
            "comparisonCountByPackage.get(a.key)",
            self.source,
        )

    def test_each_package_uses_its_most_comparable_scenario(self):
        self.assertIn(
            "raceGlanceState.selectedHypothesisByPoll[",
            self.source,
        )
        self.assertIn(
            "pollPackage.key",
            self.source,
        )
        self.assertIn(
            "] = selectedIndex;",
            self.source,
        )
        self.assertIn(
            'change.classification === "NO COMPARABLE PRIOR"',
            self.source,
        )

    def test_unavailable_comparisons_keep_column_visible(self):
        self.assertNotIn(
            '$("#race-poll-panel").classList.toggle(',
            self.source,
        )
        self.assertIn(
            'racePollPanel.classList.remove("is-no-comparison");',
            self.source,
        )
        self.assertIn(
            'hasComparableChange ? "available" : "unavailable"',
            self.source,
        )
        self.assertIn(
            '<span class="race-column-head-change">Change vs prev.</span>',
            self.source,
        )


    def test_ranked_scenario_survives_dashboard_initialization(self):
        state_start = self.source.index(
            "raceGlanceState.scaleMax ="
        )
        loop_start = self.source.index(
            "pollPackages.forEach(pollPackage => {",
            state_start,
        )
        loop_end = self.source.index(
            "const selector =",
            loop_start,
        )
        initialization = self.source[
            loop_start:loop_end
        ]

        self.assertIn(
            "const selectedIndex = Number(",
            initialization,
        )
        self.assertIn(
            "raceGlanceState.selectedHypothesisByPoll[",
            initialization,
        )
        self.assertIn(
            "!Number.isInteger(selectedIndex)",
            initialization,
        )
        self.assertIn(
            "selectedIndex >= pollPackage.events.length",
            initialization,
        )
        self.assertNotIn(
            """pollPackages.forEach(pollPackage => {
          raceGlanceState.selectedHypothesisByPoll[pollPackage.key] = 0;
        });""",
            initialization,
        )


if __name__ == "__main__":
    unittest.main()
