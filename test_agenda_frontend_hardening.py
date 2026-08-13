import copy
import unittest

from test_final_dashboard_shell import (
    agenda_evolution_payload,
    run_media_model_script,
)


class AgendaFrontendHardeningTests(unittest.TestCase):
    def build_state(self, payload):
        return run_media_model_script(
            payload,
            "(() => { const model = api.buildAgendaViewModel(); return { state: model.state, ready: Boolean(model.evolutionReady), topicCount: model.topics?.length ?? 0, evolutionCount: model.evolutionTopics?.length ?? 0, selectedTopic: model.selectedTopic?.id ?? null, selectedEvolutionTopic: model.selectedEvolutionTopic?.id ?? null }; })()",
        )

    def test_below_threshold_topics_are_not_displayed(self):
        payload = agenda_evolution_payload()

        for topic in payload["campaign_agenda"]["topics"]:
            topic["display_eligible"] = False

        for topic in payload["campaign_agenda"]["evolution"]["topics"]:
            topic["display_eligible"] = False

        result = self.build_state(payload)

        self.assertEqual(result["state"], "empty")
        self.assertEqual(result["topicCount"], 0)
        self.assertEqual(result["evolutionCount"], 0)
        self.assertIsNone(result["selectedTopic"])
        self.assertIsNone(result["selectedEvolutionTopic"])
        self.assertFalse(result["ready"])

    def test_evolution_does_not_fallback_to_below_threshold_topics(self):
        payload = agenda_evolution_payload()

        for topic in payload["campaign_agenda"]["evolution"]["topics"]:
            topic["display_eligible"] = False

        result = self.build_state(payload)

        self.assertEqual(result["state"], "ready")
        self.assertGreater(result["topicCount"], 0)
        self.assertEqual(result["evolutionCount"], 0)
        self.assertFalse(result["ready"])

    def test_malformed_base_topic_fails_closed(self):
        payload = agenda_evolution_payload()
        payload["campaign_agenda"]["topics"][0][
            "display_eligible"
        ] = "true"

        result = self.build_state(payload)

        self.assertEqual(result["state"], "invalid")
        self.assertFalse(result["ready"])

    def test_malformed_daily_count_falls_back_to_legacy_agenda(self):
        payload = agenda_evolution_payload()
        payload["campaign_agenda"]["evolution"]["topics"][0][
            "daily_activity"
        ][0]["item_count"] = "corrupted"

        result = self.build_state(payload)

        self.assertEqual(result["state"], "ready")
        self.assertGreater(result["topicCount"], 0)
        self.assertEqual(result["evolutionCount"], 0)
        self.assertFalse(result["ready"])

    def test_nonconsecutive_evolution_dates_fall_back(self):
        payload = agenda_evolution_payload()
        topic = payload["campaign_agenda"]["evolution"]["topics"][0]
        topic["daily_activity"][8]["date"] = topic[
            "daily_activity"
        ][7]["date"]

        result = self.build_state(payload)

        self.assertEqual(result["state"], "ready")
        self.assertFalse(result["ready"])
        self.assertEqual(result["evolutionCount"], 0)

    def test_evolution_topic_identity_drift_falls_back(self):
        payload = agenda_evolution_payload()
        payload["campaign_agenda"]["evolution"]["topics"][0][
            "id"
        ] = "wrong_topic"

        result = self.build_state(payload)

        self.assertEqual(result["state"], "ready")
        self.assertFalse(result["ready"])
        self.assertEqual(result["evolutionCount"], 0)

    def test_evolution_window_relationship_drift_falls_back(self):
        payload = agenda_evolution_payload()
        payload["campaign_agenda"]["evolution"][
            "latest_end"
        ] = "2026-08-08"

        result = self.build_state(payload)

        self.assertEqual(result["state"], "ready")
        self.assertFalse(result["ready"])
        self.assertEqual(result["evolutionCount"], 0)

    def test_malformed_base_agenda_is_isolated_from_media_topic_coverage(self):
        payload = agenda_evolution_payload()
        payload["campaign_agenda"]["topics"][0][
            "display_eligible"
        ] = "false"

        result = run_media_model_script(
            payload,
            '(() => { const model = api.buildMediaViewModel(); return { state: model.state, topicCoverageCount: model.topicCoverage.length }; })()',
        )

        self.assertEqual(result["state"], "empty")
        self.assertEqual(
            result["topicCoverageCount"],
            0,
        )

    def test_valid_base_agenda_still_populates_media_topic_coverage(self):
        payload = agenda_evolution_payload()

        result = run_media_model_script(
            payload,
            '(() => { const model = api.buildMediaViewModel(); return { topicCoverageCount: model.topicCoverage.length }; })()',
        )

        self.assertGreater(
            result["topicCoverageCount"],
            0,
        )

    def test_valid_evolution_remains_available(self):
        result = self.build_state(
            copy.deepcopy(
                agenda_evolution_payload()
            )
        )

        self.assertEqual(result["state"], "ready")
        self.assertTrue(result["ready"])
        self.assertGreater(result["topicCount"], 0)
        self.assertGreater(result["evolutionCount"], 0)
        self.assertEqual(
            result["selectedTopic"],
            result["selectedEvolutionTopic"],
        )


if __name__ == "__main__":
    unittest.main()
