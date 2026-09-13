from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))
FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "render_shell_candidate_v1.json"
)


def setUpModule() -> None:
    global FAMILY_LABELS, RenderModelError, TraceRenderModel, build_draft_trace
    from tools.fr27_trace import build_draft_trace as draft_builder
    from tools.fr27_trace.render import (
        FAMILY_LABELS as family_labels,
        RenderModelError as model_error,
        TraceRenderModel as render_model,
    )

    FAMILY_LABELS = family_labels
    RenderModelError = model_error
    TraceRenderModel = render_model
    build_draft_trace = draft_builder


def load_document() -> dict:
    with FIXTURE.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class RenderModelTests(unittest.TestCase):
    def test_frozen_shell_fixture_is_valid(self) -> None:
        model = TraceRenderModel.from_document(load_document())
        self.assertEqual("CANDIDATE", model.family_label)
        self.assertNotIn("public_serial", model.trace)

    def test_valid_family_labels_map_exactly(self) -> None:
        self.assertEqual(
            {
                "candidate": "CANDIDATE",
                "field": "FIELD",
                "issue": "ISSUE",
                "story": "STORY",
                "event": "EVENT",
            },
            FAMILY_LABELS,
        )
        base = load_document()
        for family, label in FAMILY_LABELS.items():
            with self.subTest(family=family):
                trace = build_draft_trace(
                    family=family,
                    detector_id="shell_mapping.v1",
                    primary_entity_ids=["synthetic:entity"],
                    observation_window={"start": "2026-08-01", "end": "2026-08-31"},
                    evidence={"datum": {"availability": "not_applicable"}},
                )
                model = TraceRenderModel.from_document(
                    {"trace": trace, "presentation": base["presentation"]}
                )
                self.assertEqual(label, model.family_label)

    def test_presentation_changes_do_not_affect_trace_identity(self) -> None:
        first_document = load_document()
        second_document = deepcopy(first_document)
        second_document["presentation"].update(
            {
                "display_label": "SYNTHETIC ENTITY BETA",
                "finding": "11 of 20 frozen observations contain a second synthetic marker.",
                "source_scope": "SECOND SYNTHETIC FIXTURE",
            }
        )
        first = TraceRenderModel.from_document(first_document)
        second = TraceRenderModel.from_document(second_document)
        self.assertEqual(
            first.trace["evidence_snapshot_hash"], second.trace["evidence_snapshot_hash"]
        )
        self.assertEqual(first.trace["trace_key"], second.trace["trace_key"])

    def test_draft_payload_has_label_and_no_public_serial(self) -> None:
        payload = TraceRenderModel.from_document(load_document()).to_payload()
        self.assertEqual("TRACE DRAFT", payload["status"])
        self.assertNotIn("serial", json.dumps(payload).lower())

    def test_required_finding_cannot_be_missing_or_empty(self) -> None:
        for value in (None, ""):
            with self.subTest(value=value):
                document = load_document()
                if value is None:
                    del document["presentation"]["finding"]
                else:
                    document["presentation"]["finding"] = value
                with self.assertRaisesRegex(RenderModelError, "finding"):
                    TraceRenderModel.from_document(document)

    def test_finding_is_one_source_line_and_length_bounded(self) -> None:
        for finding in ("line one\nline two", "x" * 121):
            with self.subTest(finding=finding[:12]):
                document = load_document()
                document["presentation"]["finding"] = finding
                with self.assertRaisesRegex(RenderModelError, "finding"):
                    TraceRenderModel.from_document(document)

    def test_optional_qualifier_is_one_line_and_length_bounded(self) -> None:
        valid = load_document()
        valid["presentation"]["qualifier"] = "Synthetic qualifier for layout validation."
        self.assertEqual(
            valid["presentation"]["qualifier"],
            TraceRenderModel.from_document(valid).qualifier,
        )
        for qualifier in ("line one\nline two", "x" * 97):
            with self.subTest(qualifier=qualifier[:12]):
                document = load_document()
                document["presentation"]["qualifier"] = qualifier
                with self.assertRaisesRegex(RenderModelError, "qualifier"):
                    TraceRenderModel.from_document(document)

    def test_render_model_rejects_invalid_trace(self) -> None:
        document = load_document()
        document["trace"]["family"] = "poll"
        with self.assertRaisesRegex(RenderModelError, "invalid TRACE"):
            TraceRenderModel.from_document(document)

    def test_render_model_rejects_unknown_presentation_fields(self) -> None:
        document = load_document()
        document["presentation"]["political_score"] = 99
        with self.assertRaisesRegex(RenderModelError, "unknown fields"):
            TraceRenderModel.from_document(document)


if __name__ == "__main__":
    unittest.main()
