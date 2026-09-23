import json
import unittest
from pathlib import Path

from update_news_corpus_ledger import corpus_counts


ROOT = Path(__file__).resolve().parent


class HudCorpusCountsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hybrid = (
            ROOT / "assets" / "hybrid-dashboard.js"
        ).read_text(encoding="utf-8")

        cls.shells = {
            name: (ROOT / name).read_text(encoding="utf-8")
            for name in (
                "index.html",
                "en/index.html",
            )
        }

        cls.en = (
            ROOT / "locales" / "en.js"
        ).read_text(encoding="utf-8")

        cls.fr = (
            ROOT / "locales" / "fr.js"
        ).read_text(encoding="utf-8")

        cls.wire = json.loads(
            (ROOT / "news_wire.json").read_text(
                encoding="utf-8"
            )
        )

        cls.ledger = json.loads(
            (ROOT / "news_corpus_ledger.json").read_text(
                encoding="utf-8"
            )
        )

    def test_news_wire_exposes_valid_corpus_counts(self):
        corpus = self.wire.get("corpus_counts")

        self.assertIsInstance(corpus, dict)

        self.assertEqual(
            corpus,
            corpus_counts(self.ledger),
        )

        for field in (
            "accepted_election_news",
            "candidate_watch",
            "accepted_news_publishers",
        ):
            with self.subTest(field=field):
                self.assertIsInstance(
                    corpus.get(field),
                    int,
                )
                self.assertGreaterEqual(
                    corpus[field],
                    0,
                )

        self.assertGreaterEqual(
            corpus["accepted_election_news"],
            len(self.wire["election_news"]),
        )
        self.assertGreaterEqual(
            corpus["candidate_watch"],
            len(self.wire["candidate_watch"]),
        )

    def test_media_pulse_visible_metrics_remain_rolling(self):
        self.assertIn(
            "value: model.electionNewsCount",
            self.hybrid,
        )
        self.assertIn(
            "model.acceptedNewsPublisherCount",
            self.hybrid,
        )
        self.assertIn(
            "value: model.activityItemCount",
            self.hybrid,
        )
        self.assertIn(
            "value: model.candidateWatchCount",
            self.hybrid,
        )

    def test_hybrid_projects_corpus_counts_for_hud_only(self):
        for token in (
            "payload.corpus_counts",
            "corpusAcceptedNewsCount",
            "corpusCandidateWatchCount",
            "corpusPublisherCount",
            '"data-corpus-accepted-news"',
            '"data-corpus-publishers"',
            '"data-corpus-candidate-watch"',
        ):
            with self.subTest(token=token):
                self.assertIn(
                    token,
                    self.hybrid,
                )

    def test_both_shells_prefer_cumulative_hud_metrics(self):
        for name, shell in self.shells.items():
            with self.subTest(shell=name):
                self.assertIn(
                    'fr27HudExtractCorpusMetric(',
                    shell,
                )
                self.assertIn(
                    '"data-corpus-accepted-news"',
                    shell,
                )
                self.assertIn(
                    '"data-corpus-publishers"',
                    shell,
                )
                self.assertIn(
                    '"data-corpus-candidate-watch"',
                    shell,
                )

                # Cumulative HUD fields must fail closed rather than
                # silently substitute rolling Media Pulse values.
                for rolling_key in (
                    "media_pulse.metric.accepted_news",
                    "media_pulse.metric.publishers",
                    "media_pulse.metric.candidate_watch",
                ):
                    self.assertNotIn(
                        'fr27HudExtractExactMetric(\n'
                        f'        "{rolling_key}"',
                        shell,
                    )

                # Recent 14-day activity deliberately remains rolling.
                self.assertIn(
                    '"media_pulse.metric.recent_14d"',
                    shell,
                )

    def test_hud_cumulative_semantics_are_explained(self):
        for locale in (
            self.en,
            self.fr,
        ):
            self.assertIn(
                '"hud.accepted_news_explanation"',
                locale,
            )
            self.assertIn(
                '"hud.candidate_watch_explanation"',
                locale,
            )
            self.assertIn(
                '"hud.publishers_explanation"',
                locale,
            )


if __name__ == "__main__":
    unittest.main()
