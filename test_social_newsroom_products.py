import json
import re
import unittest
from pathlib import Path

from social import newsroom_products as MODULE


ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads(
        (ROOT / name).read_text(
            encoding="utf-8"
        )
    )


class NewsroomProductTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.issues = load(
            "issue_coverage_history.json"
        )
        cls.agenda = load(
            "agenda_coverage_history.json"
        )

    def products(self, locale="fr"):
        return (
            MODULE.build_newsroom_products(
                issue_payload=self.issues,
                agenda_payload=self.agenda,
                locale=locale,
            )
        )

    def test_builds_daily_and_weekly_products(self):
        products = self.products()

        keys = {
            (
                product.family,
                product.rank_kind,
                product.window_mode,
            )
            for product in products
        }

        expected = {
            (
                family,
                rank,
                window,
            )
            for family in (
                "issues",
                "agenda",
            )
            for rank in (
                "movers",
                "dominance",
            )
            for window in (
                "complete_day",
                "complete_week",
            )
        }

        self.assertEqual(
            keys,
            expected,
        )

    def test_no_fake_24h_language(self):
        for locale in (
            "fr",
            "en",
        ):
            for product in self.products(
                locale
            ):
                text = product.text.lower()

                self.assertNotIn(
                    "24h",
                    text,
                )
                self.assertNotIn(
                    "24 h",
                    text,
                )
                self.assertNotIn(
                    "last 24",
                    text,
                )

    def test_normal_posts_do_not_expose_raw_counts(self):
        ratio = re.compile(
            r"\b\d+/\d+\b"
        )

        for locale in (
            "fr",
            "en",
        ):
            for product in self.products(
                locale
            ):
                self.assertIsNone(
                    ratio.search(
                        product.text
                    )
                )

    def test_every_product_fits_x(self):
        for locale in (
            "fr",
            "en",
        ):
            for product in self.products(
                locale
            ):
                self.assertLessEqual(
                    product.weighted_length,
                    MODULE.MAX_X_WEIGHTED_LENGTH,
                    msg=(
                        product.product_id
                        + "\n"
                        + product.text
                    ),
                )

                self.assertEqual(
                    product.weighted_length,
                    MODULE.weighted_x_length(
                        product.text
                    ),
                )

    def test_agenda_products_exclude_polling_topic(self):
        for product in self.products():
            if product.family != "agenda":
                continue

            ids = {
                row.entity_id
                for row in product.rows
            }

            self.assertNotIn(
                "polls_race",
                ids,
            )

    def test_movers_are_ranked_by_displayed_delta(self):
        for product in self.products():
            if (
                product.rank_kind
                != "movers"
            ):
                continue

            magnitudes = [
                abs(row.display_delta)
                for row in product.rows
            ]

            self.assertEqual(
                magnitudes,
                sorted(
                    magnitudes,
                    reverse=True,
                ),
            )

    def test_dominance_uses_current_share(self):
        for product in self.products():
            if (
                product.rank_kind
                != "dominance"
            ):
                continue

            shares = [
                row.current_display
                for row in product.rows
            ]

            self.assertEqual(
                shares,
                sorted(
                    shares,
                    reverse=True,
                ),
            )

    def test_weekly_windows_are_complete_monday_sunday(self):
        for product in self.products():
            if (
                product.window_mode
                != "complete_week"
            ):
                continue

            from datetime import date

            current_start = (
                date.fromisoformat(
                    product.current_start
                )
            )
            current_end = (
                date.fromisoformat(
                    product.current_end
                )
            )
            previous_start = (
                date.fromisoformat(
                    product.previous_start
                )
            )
            previous_end = (
                date.fromisoformat(
                    product.previous_end
                )
            )

            self.assertEqual(
                current_start.weekday(),
                0,
            )
            self.assertEqual(
                current_end.weekday(),
                6,
            )
            self.assertEqual(
                previous_start.weekday(),
                0,
            )
            self.assertEqual(
                previous_end.weekday(),
                6,
            )

    def test_language_does_not_claim_electoral_winners(self):
        prohibited = (
            "winner",
            "loser",
            "momentum",
            "popularité",
            "gagne l’élection",
            "perd l’élection",
        )

        for locale in (
            "fr",
            "en",
        ):
            for product in self.products(
                locale
            ):
                text = product.text.lower()

                for phrase in prohibited:
                    self.assertNotIn(
                        phrase,
                        text,
                    )

    def test_dominance_shows_current_period_only(self):
        for locale in (
            "fr",
            "en",
        ):
            for product in self.products(
                locale
            ):
                lines = product.text.splitlines()

                self.assertGreaterEqual(
                    len(lines),
                    2,
                )

                period_line = lines[1]

                if product.rank_kind == "dominance":
                    self.assertNotIn(
                        " vs ",
                        period_line,
                    )

                if product.rank_kind == "movers":
                    self.assertIn(
                        " vs ",
                        period_line,
                    )

    def test_zero_delta_movers_render_as_stable(self):
        found = False

        for locale in (
            "fr",
            "en",
        ):
            for product in self.products(
                locale
            ):
                if product.rank_kind != "movers":
                    continue

                zero_rows = [
                    row
                    for row in product.rows
                    if row.display_delta == 0
                ]

                if not zero_rows:
                    continue

                found = True

                for row in zero_rows:
                    self.assertIn(
                        f"• {row.label} — stable",
                        product.text,
                    )

        self.assertTrue(found)

    def test_products_are_deterministic(self):
        first = self.products()
        second = self.products()

        self.assertEqual(
            first,
            second,
        )


if __name__ == "__main__":
    unittest.main()
