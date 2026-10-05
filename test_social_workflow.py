from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).parent
    / ".github"
    / "workflows"
    / "publish-x-fr.yml"
)


class SocialWorkflowTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(
            encoding="utf-8-sig"
        )

    def test_schedule_is_guarded_by_safety_switch(self):
        self.assertIn(
            (
                "github.event_name == "
                "'workflow_dispatch' ||"
            ),
            self.text,
        )

        self.assertIn(
            (
                "vars.FR27_SOCIAL_ENABLED "
                "== 'true'"
            ),
            self.text,
        )

    def test_production_checkout_is_main(self):
        self.assertIn(
            "ref: main",
            self.text,
        )

    def test_daily_queue_build_schedule_exists(self):
        self.assertIn(
            "cron: '25 8 * * *'",
            self.text,
        )

        for cron in (
            "45 8 * * *",
            "15 10 * * *",
            "30 11 * * *",
            "15 12 * * *",
            "30 14 * * *",
            "45 16 * * *",
            "30 19 * * *",
        ):
            self.assertIn(
                f"cron: '{cron}'",
                self.text,
            )

    def test_dynamic_updates_are_capped(self):
        self.assertIn(
            "--max-posts 1",
            self.text,
        )

        self.assertIn(
            "--daily-limit 3",
            self.text,
        )

    def test_first_bootstrap_can_create_state_branch(self):
        self.assertIn(
            "--orphan",
            self.text,
        )

        self.assertIn(
            "social-assets",
            self.text,
        )

        self.assertIn(
            "HEAD:social-assets",
            self.text,
        )

    def test_live_bootstrap_is_create_once(self):
        self.assertIn(
            "Refuse live bootstrap over existing state",
            self.text,
        )

        self.assertIn(
            "steps.state.outputs.exists == 'true'",
            self.text,
        )

        self.assertIn(
            (
                "social-assets already exists; "
                "live bootstrap is create-once only."
            ),
            self.text,
        )

    def test_full_dry_run_never_requires_buffer(self):
        self.assertIn(
            "mode == 'full-dry-run'",
            self.text,
        )

        self.assertIn(
            "--dry-run",
            self.text,
        )

        self.assertIn(
            "fr27-x-full-dry-run",
            self.text,
        )

    def test_custom_social_graphic_renderers_are_not_used(self):
        forbidden = (
            "render_visibility_graphic.py",
            "render_editorial_graphic.py",
            "playwright install",
            "Publish visual post",
        )

        for value in forbidden:
            self.assertNotIn(
                value,
                self.text,
            )

    def test_state_is_only_persisted_for_live_execution(self):
        self.assertIn(
            (
                "steps.mode.outputs.publish "
                "== 'true'"
            ),
            self.text,
        )

        self.assertIn(
            "Persist unified social state",
            self.text,
        )

    def test_core_slot_uses_immutable_queue(self):
        self.assertIn(
            (
                "python -B "
                "social/daily_queue.py slot"
            ),
            self.text,
        )

    def test_workflow_is_serialized(self):
        self.assertIn(
            "group: fr27-social-publish",
            self.text,
        )

        self.assertIn(
            "cancel-in-progress: false",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
