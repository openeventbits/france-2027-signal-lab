from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TRACE_ROOT = Path(__file__).resolve().parents[1]
RENDER_ROOT = TRACE_ROOT / "render"
FIXTURE = TRACE_ROOT / "fixtures" / "render_shell_candidate_v1.json"
sys.path.insert(0, str(REPOSITORY_ROOT))


def setUpModule() -> None:
    global OutputPathError, TraceRenderModel, fixture_path, resolve_output_path
    from tools.fr27_trace.render import (
        OutputPathError as path_error,
        TraceRenderModel as render_model,
        fixture_path as fixture_guard,
        resolve_output_path as output_guard,
    )

    OutputPathError = path_error
    TraceRenderModel = render_model
    fixture_path = fixture_guard
    resolve_output_path = output_guard


class _ShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.footer_zones: list[str] = []
        self.svg_classes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "section" and "data-footer-zone" in attributes:
            self.footer_zones.append(attributes["data-footer-zone"] or "")
        if tag == "svg":
            self.svg_classes.extend((attributes.get("class") or "").split())


class RenderSafetyTests(unittest.TestCase):
    def test_output_guard_accepts_output_root_descendants(self) -> None:
        relative = resolve_output_path("_trace_output/task-02/shell.png")
        absolute = resolve_output_path(
            REPOSITORY_ROOT / "_trace_output" / "nested" / "shell.PNG"
        )
        self.assertTrue(relative.is_relative_to(REPOSITORY_ROOT / "_trace_output"))
        self.assertTrue(absolute.is_relative_to(REPOSITORY_ROOT / "_trace_output"))

    def test_output_guard_rejects_traversal_and_outside_paths(self) -> None:
        invalid = (
            "../foo.png",
            "_trace_output/nested/../../foo.png",
            REPOSITORY_ROOT / "outside.png",
            REPOSITORY_ROOT / "_trace_output",
            "_trace_output/not-a-png.txt",
        )
        for requested in invalid:
            with self.subTest(requested=str(requested)):
                with self.assertRaises(OutputPathError):
                    resolve_output_path(requested)

    def test_fixture_guard_rejects_live_or_outside_data(self) -> None:
        self.assertEqual(FIXTURE.resolve(), fixture_path(FIXTURE))
        for requested in (
            REPOSITORY_ROOT / "polls.json",
            REPOSITORY_ROOT / "assets" / "data" / "polls.json",
            TRACE_ROOT / "fixtures" / "nested" / ".." / ".." / "contract.py",
        ):
            with self.subTest(requested=str(requested)):
                with self.assertRaises(OutputPathError):
                    fixture_path(requested)

    def test_fixed_footer_zones_exist_in_required_order(self) -> None:
        parser = _ShellParser()
        parser.feed((RENDER_ROOT / "shell.html").read_text(encoding="utf-8"))
        self.assertEqual(["source", "method", "brand"], parser.footer_zones)
        css = (RENDER_ROOT / "shell.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: 45fr 35fr 20fr", css)
        self.assertIn("france2027.app", (RENDER_ROOT / "shell.html").read_text(encoding="utf-8"))

    def test_footer_signature_uses_standalone_signal_glyph(self) -> None:
        parser = _ShellParser()
        html = (RENDER_ROOT / "shell.html").read_text(encoding="utf-8")
        parser.feed(html)
        self.assertIn("signature-glyph", parser.svg_classes)
        self.assertIn('<span class="brand-url">france2027.app</span>', html)
        self.assertNotIn("app-icon", html)
        self.assertNotIn("circle-badge", html)

    def test_footer_typography_preserves_signature_hierarchy(self) -> None:
        css = (RENDER_ROOT / "shell.css").read_text(encoding="utf-8")
        self.assertIn(".footer-label {\n  color: var(--muted-soft);\n  font-size: 9px", css)
        self.assertIn(".footer-zone {", css)
        self.assertIn("font-size: 9px", css[css.index(".footer-zone {"):css.index(".footer-method,")])
        brand_url = css[css.index(".brand-url {"):]
        self.assertIn("font-size: 12px", brand_url)
        self.assertIn("font-weight: 700", brand_url)

    def test_field_is_open_and_temporal_cues_are_neutral(self) -> None:
        html = (RENDER_ROOT / "shell.html").read_text(encoding="utf-8")
        css = (RENDER_ROOT / "shell.css").read_text(encoding="utf-8")
        self.assertNotIn(">T0<", html)
        self.assertNotIn(">T1<", html)
        self.assertIn(">WINDOW START<", html)
        self.assertIn(">WINDOW END<", html)
        field_css = css[css.index(".trace-field {"):css.index(".field-heading,")]
        self.assertIn("border: 0", field_css)
        self.assertIn("border-radius: 0", field_css)
        self.assertIn("background: transparent", field_css)

    def test_entity_label_uses_structural_not_evidence_color(self) -> None:
        css = (RENDER_ROOT / "shell.css").read_text(encoding="utf-8")
        entity_css = css[css.index(".entity-label {"):css.index(".finding-text {")]
        self.assertIn("color: var(--muted)", entity_css)
        self.assertNotIn("color: var(--cyan)", entity_css)

    def test_frozen_geometry_and_six_lane_limit_are_explicit(self) -> None:
        css = (RENDER_ROOT / "shell.css").read_text(encoding="utf-8")
        for rule in (
            "width: 1280px",
            "height: 720px",
            "inset: 16px",
            ".header-divider { top: 72px; }",
            "top: 168px",
            "height: 456px",
            ".footer-divider { top: 648px; }",
            "grid-template-rows: repeat(6, 1fr)",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, css)

    def test_task_02_renderer_sources_reference_no_live_data(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(RENDER_ROOT.iterdir())
            if path.suffix in {".py", ".js", ".cjs", ".html", ".css"}
        ).lower()
        for forbidden in (
            "polls.json",
            "candidate_registry",
            "fetch(",
            "http://",
            "https://",
            "assets/",
            ".github/",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_loading_render_fixture_does_not_change_protected_files(self) -> None:
        protected = [
            REPOSITORY_ROOT / "index.html",
            REPOSITORY_ROOT / ".github" / "scripts" / "capture-og-cover.cjs",
            REPOSITORY_ROOT / ".github" / "workflows" / "refresh-og-cover.yml",
            REPOSITORY_ROOT / "assets" / "final-dashboard-shell.css",
        ]
        before = {path: path.read_bytes() for path in protected}
        with fixture_path(FIXTURE).open(encoding="utf-8") as fixture_file:
            TraceRenderModel.from_document(json.load(fixture_file))
        after = {path: path.read_bytes() for path in protected}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
