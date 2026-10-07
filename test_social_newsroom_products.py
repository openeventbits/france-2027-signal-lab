import json
import unittest
from dataclasses import replace
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

        # Availability is conditional on the canonical displayed rows, not
        # guaranteed by having a daily/weekly history artifact. Assert every
        # qualified product exists and every unqualified product is absent.
        expected = set()
        for family, payload, build in (
            ("issues", self.issues, MODULE.contract.build_issue_metric_snapshot),
            ("agenda", self.agenda, MODULE.contract.build_agenda_metric_snapshot),
        ):
            for window in ("complete_day", "complete_week"):
                snapshot = build(payload, window_mode=window)
                excluded = MODULE.AGENDA_EXCLUDED_SOCIAL_IDS if family == "agenda" else ()
                movers = MODULE.contract.rank_movers(snapshot, limit=1,
                    excluded_entity_ids=excluded, require_full=True)
                if len(movers) == 1 and abs(movers[0].display_delta) >= .1:
                    expected.add((family, "movers", window))
                limit = 1
                leaders = MODULE.contract.rank_current_share(snapshot, limit=limit,
                    excluded_entity_ids=excluded, require_full=True)
                if len(leaders) == limit and sum(row.current_display > 0 for row in leaders) >= 1:
                    expected.add((family, "dominance", window))

        self.assertEqual(
            keys,
            expected,
        )

    def test_insufficient_displayed_evidence_suppresses_products(self):
        for family, payload, build in (
            ("issues", self.issues, MODULE.contract.build_issue_metric_snapshot),
            ("agenda", self.agenda, MODULE.contract.build_agenda_metric_snapshot),
        ):
            snapshot = build(payload, window_mode="complete_day")
            silent = replace(snapshot, rows=tuple(replace(row,
                current_display=0.0, display_delta=0.0) for row in snapshot.rows))
            qualified = replace(snapshot, rows=tuple(replace(row,
                current_display=1.0, display_delta=1.0) for row in snapshot.rows))
            for rank in ("movers", "dominance"):
                with self.subTest(family=family, rank=rank):
                    self.assertIsNone(MODULE._make_product(snapshot=silent, family=family,
                        rank_kind=rank, locale="fr"))
                    self.assertIsNotNone(MODULE._make_product(snapshot=qualified, family=family,
                        rank_kind=rank, locale="fr"))

    def test_daily_headline_matches_actual_complete_dates(self):
        for product in self.products():
            expected = "7 JOURS · VS 7 JOURS PRÉCÉDENTS" if product.window_mode == "complete_week" else "24 H · VS 24 H PRÉCÉDENTES"
            if product.rank_kind == "movers":
                self.assertIn(expected, product.text)
            self.assertEqual(len(product.rows), 1)

    def test_evidence_uses_source_day_contract(self):
        for product in self.products():
            row = product.rows[0]
            self.assertIn("jours-sources", product.text)
            self.assertNotIn("articles classés", product.text)
            if product.family == "issues":
                self.assertIn("Un même article peut relever de plusieurs enjeux.", product.text)
            if product.rank_kind == "movers":
                self.assertIn(f"contre {row.previous_evidence}/{row.previous_denominator}", product.text)
                self.assertIn("Écart :", product.text)

    def test_reference_shape_and_signed_delta(self):
        snapshot = MODULE.contract.build_agenda_metric_snapshot(self.agenda, window_mode="complete_week")
        reference = replace(snapshot.rows[0], entity_id="selection_strategy",
            label_fr="Primaires et stratégies partisanes", current_evidence=98,
            current_denominator=165, current_display=59.4, previous_evidence=197,
            previous_denominator=265, previous_display=74.3, display_delta=-14.9)
        snapshot = replace(snapshot, rows=(reference,))
        rendered = MODULE._make_product(snapshot=snapshot, family="agenda", rank_kind="movers", locale="fr")
        self.assertIn("Primaires et stratégies partisanes : 98/165 jours-sources affectés aux thèmes de l’agenda (59,4 %), contre 197/265 (74,3 %). Écart : −14,9 pts.", rendered.text)
        positive = replace(reference, display_delta=14.9, current_display=74.3, previous_display=59.4,
                           current_evidence=197, current_denominator=265, previous_evidence=98, previous_denominator=165)
        result = MODULE._make_product(snapshot=replace(snapshot, rows=(positive,)), family="agenda", rank_kind="movers", locale="fr")
        self.assertIn("Écart : +14,9 pts.", result.text)

    def test_issue_positive_and_negative_evidence(self):
        snapshot = MODULE.contract.build_issue_metric_snapshot(self.issues, window_mode="complete_day")
        for delta in (6.3, -6.3):
            row = replace(snapshot.rows[0], label_fr="Pouvoir d’achat", current_evidence=23,
                current_denominator=63, previous_evidence=19, previous_denominator=63,
                current_display=36.5, previous_display=30.2, display_delta=delta)
            result = MODULE._make_product(snapshot=replace(snapshot, rows=(row,)), family="issues", rank_kind="movers", locale="fr")
            self.assertIn("présence dans 23 des 63 jours-sources", result.text)
            self.assertIn("contre 19/63 (30,2 %)", result.text)
            self.assertIn(MODULE._fr_delta(delta), result.text)

    def test_daily_gap_does_not_claim_previous_24h(self):
        snapshot = MODULE.contract.build_agenda_metric_snapshot(self.agenda, window_mode="complete_day")
        snapshot = replace(snapshot, previous_start="2026-09-01", previous_end="2026-09-01")
        result = MODULE._make_product(snapshot=snapshot, family="agenda", rank_kind="dominance", locale="fr")
        self.assertNotIn("24 H", result.text)

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

    def test_dominance_has_no_invented_comparison(self):
        for product in self.products():
            if product.rank_kind == "dominance":
                self.assertNotIn("contre", product.text)
                self.assertNotIn("Écart", product.text)
                self.assertIn("le thème le plus présent", product.text)

    def test_french_posts_have_no_dashboard_clutter(self):
        for product in self.products():
            for clutter in ("↑", "↓", "👀", "📡", "📊", " & "):
                self.assertNotIn(clutter, product.text)

    def test_english_products_keep_the_existing_ranked_format(self):
        for product in self.products("en"):
            expected = 3 if product.family == "agenda" and product.rank_kind == "dominance" else 5
            self.assertEqual(len(product.rows), expected)
            self.assertNotIn("24 H", product.text)
            self.assertIn(MODULE._boundary(product.family, "en"), product.text)
            if product.rank_kind == "movers":
                self.assertIn(" vs ", product.text.splitlines()[1])
                for row in product.rows:
                    if row.display_delta == 0:
                        self.assertIn(f"• {row.label} — stable", product.text)

    def test_products_are_deterministic(self):
        first = self.products()
        second = self.products()

        self.assertEqual(
            first,
            second,
        )


if __name__ == "__main__":
    unittest.main()
