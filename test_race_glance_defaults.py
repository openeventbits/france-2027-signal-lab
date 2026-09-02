import json
from pathlib import Path
import shutil
import subprocess
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
            "const allPollPackages =",
            self.source,
        )
        self.assertIn(
            "buildRacePollPackages(validEvents);",
            self.source,
        )
        self.assertIn(
            "const pollPackages = rankRacePollPackages(",
            self.source,
        )
        self.assertIn(
            "allPollPackages,",
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
            '"dashboard.vs_prior_match",',
            self.source,
        )
        self.assertIn('"VS PRIOR MATCH"', self.source)
        self.assertIn(
            'data-fr27-tooltip="${escapeAttribute(comparisonExplanation)}"',
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

    def test_poll_tabs_show_compact_wave_identity(self):
        self.assertIn("full.textContent = fullLabel;", self.source)
        self.assertIn(
            "const shortLabel = racePollTabShortLabel(pollPackage);",
            self.source,
        )
        self.assertIn("short.textContent = shortLabel;", self.source)
        self.assertIn("button.setAttribute(\"aria-label\", fullLabel);", self.source)
        self.assertIn("button.dataset.fr27Tooltip = fullLabel;", self.source)

        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("Node.js is required for Race at a Glance tests")
        start = self.source.index("function compactRacePollDate(")
        end = self.source.index("function raceScenarioLabel(", start)
        helpers = self.source[start:end]
        packages = [
            {"pollster": "Harris", "fieldwork_end": "2026-08-19"},
            {"pollster": "Harris", "fieldwork_end": "2026-08-22"},
            {
                "pollster": "Harris Interactive",
                "fieldwork_end": "2026-08-19",
            },
        ]
        script = (
            helpers
            + "\nconst packages = "
            + json.dumps(packages)
            + ";\nconsole.log(JSON.stringify({"
            + "full: packages.map(racePollTabLabel),"
            + "short: packages.map(racePollTabShortLabel)"
            + "}));"
        )
        result = subprocess.run(
            [node, "-e", script],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        labels = json.loads(result.stdout)
        full_labels = labels["full"]
        short_labels = labels["short"]

        self.assertEqual(
            [label.split()[-2:] for label in full_labels[:2]],
            [
                ["19", "Aug"],
                ["22", "Aug"],
            ],
        )
        self.assertTrue(
            all(label.startswith("Harris") for label in full_labels)
        )
        self.assertEqual(
            full_labels[2],
            "Harris Interactive · 19 Aug",
        )
        self.assertEqual(
            short_labels,
            [
                "Harris · 19 Aug",
                "Harris · 22 Aug",
                "Harris I. · 19 Aug",
            ],
        )
        self.assertEqual(
            len(full_labels),
            len(set(full_labels)),
        )
        self.assertEqual(
            len(short_labels),
            len(set(short_labels)),
        )


if __name__ == "__main__":
    unittest.main()
