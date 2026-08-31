from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
ANNOTATED_SOURCES = (
    INDEX,
    ROOT / "assets" / "hybrid-dashboard.js",
    ROOT / "assets" / "candidate-signals-workspace.js",
    ROOT / "assets" / "topic-coverage-modal.js",
    ROOT / "assets" / "election-coverage-modal.js",
)

FROZEN_TYPES = {
    "display",
    "panel-title",
    "module-title",
    "kicker",
    "item-title",
    "row-label",
    "field-label",
    "nav-label",
    "action-label",
    "body",
    "meta",
    "status-label",
    "scale-label",
    "data",
    "key-data",
    "focal-data",
}

DEPRECATED_TYPES = {
    "workspace-title",
    "section-title",
    "primary-reading",
    "micro",
    "badge",
    "chart-label",
    "major-data",
    "instrument",
    "dense",
    "compact",
    "small",
}


class ShellTypeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.by_id = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.by_id[values["id"]] = values.get("data-fr27-type")


class SemanticTypographyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {
            path: path.read_text(encoding="utf-8")
            for path in ANNOTATED_SOURCES
        }
        cls.index = cls.sources[INDEX]
        cls.hybrid = cls.sources[ROOT / "assets" / "hybrid-dashboard.js"]

    def test_every_literal_type_uses_the_exact_frozen_enum(self):
        found = set()
        literal_pattern = re.compile(r'data-fr27-type=["\']([^"\']+)["\']')
        setter_pattern = re.compile(
            r'setAttribute\(["\']data-fr27-type["\']\s*,\s*["\']([^"\']+)["\']'
        )

        for path, source in self.sources.items():
            values = literal_pattern.findall(source) + setter_pattern.findall(source)
            for value in values:
                if "${" in value:
                    continue
                with self.subTest(path=path.name, value=value):
                    self.assertIn(value, FROZEN_TYPES)
                    self.assertNotRegex(value, r"[\s,]")
                found.add(value)

        self.assertEqual(found, FROZEN_TYPES)

    def test_a_source_element_cannot_declare_two_type_attributes(self):
        opening_tag = re.compile(r"<[^!][^>]*>", re.DOTALL)
        for path, source in self.sources.items():
            for tag in opening_tag.findall(source):
                with self.subTest(path=path.name, tag=tag[:120]):
                    self.assertLessEqual(tag.count("data-fr27-type="), 1)

    def test_whitespace_comma_and_deprecated_values_are_rejected(self):
        rejected = {
            "panel-title module-title",
            "panel-title,module-title",
            " panel-title",
            "panel-title ",
            *DEPRECATED_TYPES,
        }
        for value in rejected:
            with self.subTest(value=value):
                self.assertNotIn(value, FROZEN_TYPES)

        combined = "\n".join(self.sources.values())
        for value in DEPRECATED_TYPES:
            self.assertNotRegex(
                combined,
                rf'data-fr27-type=["\']{re.escape(value)}["\']',
            )

    def test_required_static_shell_nodes_have_canonical_roles(self):
        parser = ShellTypeParser()
        parser.feed(self.index)
        expected = {
            "what-changed-title": "panel-title",
            "race-glance-title": "panel-title",
            "top-media-pulse-title": "panel-title",
            "signal-desk-title": "panel-title",
            "closest-runoff-title": "panel-title",
            "signal-tab-election": "nav-label",
            "signal-tab-agenda": "nav-label",
            "signal-tab-candidates": "nav-label",
            "signal-tab-fact-checks": "nav-label",
        }
        for element_id, role in expected.items():
            with self.subTest(element_id=element_id):
                self.assertEqual(parser.by_id.get(element_id), role)

        self.assertIn(
            '<h1 data-fr27-type="display">FRANCE 2027 <span>SIGNAL LAB</span></h1>',
            self.index,
        )
        self.assertRegex(
            self.index,
            r'class="clock-count" data-fr27-type="focal-data"',
        )

    def test_tabs_are_navigation_labels_and_never_title_roles(self):
        tab_fragments = re.findall(
            r'<(?:button|a)[^>]*(?:role="tab"|class="[^"]*tab[^"]*")[^>]*>',
            "\n".join(self.sources.values()),
            re.DOTALL,
        )
        self.assertTrue(tab_fragments)
        for fragment in tab_fragments:
            if "data-fr27-type" not in fragment:
                continue
            with self.subTest(fragment=fragment[:140]):
                self.assertIn('data-fr27-type="nav-label"', fragment)
                self.assertNotRegex(fragment, r'data-fr27-type="(?:panel|module|item)-title"')

    def test_race_renderer_keeps_names_labels_and_values_distinct(self):
        self.assertRegex(
            self.index,
            r'class="candidate"\s+data-fr27-type="row-label"',
        )
        self.assertRegex(
            self.index,
            r'class="score"\s+data-fr27-type="data"',
        )
        self.assertRegex(
            self.index,
            r'class="race-column-head-candidate"\s+data-fr27-type="field-label"',
        )
        self.assertRegex(
            self.index,
            r'<strong data-fr27-type="data">\$\{escapeHtml\(changeGlyph \+ formattedChange\.value\)\}</strong>',
        )

    def test_signal_desk_keeps_navigation_content_state_and_actions_distinct(self):
        for element_id in (
            "signal-tab-election",
            "signal-tab-agenda",
            "signal-tab-candidates",
            "signal-tab-fact-checks",
        ):
            self.assertRegex(
                self.index,
                rf'id="{element_id}"[^>]+data-fr27-type="nav-label"',
            )

        self.assertIn(
            '<h3 class="claims-archive-wire-title" id="claim-wire-title" data-fr27-type="module-title">CLAIM WIRE</h3>',
            self.index,
        )
        self.assertRegex(
            self.index,
            r'class="signal-source"\s+data-fr27-type="item-title"',
        )
        self.assertRegex(
            self.index,
            r'class="campaign-agenda-detail-kicker"\s+data-fr27-type="kicker"',
        )
        self.assertRegex(
            self.index,
            r'class="campaign-agenda-link"\s+data-fr27-type="action-label"',
        )
        self.assertRegex(
            self.index,
            r'class="claim-text"[\s\S]*?data-fr27-type="item-title"',
        )
        self.assertRegex(
            self.index,
            r'class="claim-rating[^"]*"\s+data-fr27-type="status-label"',
        )
        self.assertRegex(
            self.index,
            r'class="claim-expand"\s+data-fr27-type="action-label"',
        )
        self.assertNotRegex(
            self.index,
            r'class="(?:signal-state|claims-state)(?: error)?"(?!\s+data-fr27-type="status-label")',
        )

    def test_hud_keeps_zones_readings_metadata_statuses_and_commands_distinct(self):
        for label in (
            "LIVE TIME",
            "COUNTDOWN",
            "INFRASTRUCTURE / METHODOLOGY",
            "SOURCE UNIVERSE",
            "DATASET SCALE",
            "UTILITY",
        ):
            self.assertRegex(
                self.index,
                rf'data-fr27-type="module-title">\s*{re.escape(label)}\s*<',
            )

        self.assertRegex(
            self.index,
            r'id="fr27-hud-paris-time"\s+data-fr27-type="focal-data"',
        )
        self.assertRegex(
            self.index,
            r'id="fr27-hud-countdown-days"[\s\S]*?data-fr27-type="focal-data"',
        )
        self.assertRegex(
            self.index,
            r'class="fr27-zone-meta"\s+data-fr27-type="meta"',
        )
        self.assertRegex(
            self.index,
            r'class="fr27-linear-system-value[^"]*"\s+data-fr27-type="status-label"',
        )

        for control in (
            "fr27-app-hud-toggle",
            "fr27-hud-email-toggle",
            "fr27-hud-share",
            "fr27-hud-info-toggle",
            "fr27-hud-contact-copy",
        ):
            self.assertRegex(
                self.index,
                rf'(?:id="{control}"[\s\S]{{0,120}}data-fr27-type="action-label"|data-fr27-type="action-label"[\s\S]{{0,120}}id="{control}")',
            )

        self.assertIn(
            'hudPollsNode.setAttribute("data-fr27-type", "key-data");',
            self.index,
        )
        self.assertIn(
            'node.setAttribute("data-fr27-type", "key-data");',
            self.index,
        )
    def test_context_strip_values_are_assigned_per_renderer_semantics(self):
        context_renderer = self.index[
            self.index.index("function renderContextStrip("):
            self.index.index("function validateNewsWirePayload(")
        ]
        self.assertIn(
            'setAttribute("data-fr27-type", "item-title")',
            context_renderer,
        )
        self.assertIn('? "key-data" : "meta"', context_renderer)
        self.assertGreaterEqual(context_renderer.count('"data-fr27-type", "meta"'), 3)
        for element_id in (
            "context-milestone-value",
            "context-poll-value",
            "context-coverage-value",
            "context-status-value",
        ):
            self.assertRegex(
                self.index,
                rf'id="{element_id}" data-fr27-type="meta"',
            )

    def test_modal_main_titles_are_panel_titles(self):
        for filename in (
            "assets/topic-coverage-modal.js",
            "assets/election-coverage-modal.js",
        ):
            source = (ROOT / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertRegex(
                    source,
                    r'<h2[^>]+data-fr27-type="panel-title"',
                )

    def test_status_and_meta_are_separate_contracts(self):
        combined = "\n".join(self.sources.values())
        self.assertIn('data-fr27-type="status-label"', combined)
        self.assertIn('data-fr27-type="meta"', combined)
        self.assertNotIn('data-fr27-type="status-label meta"', combined)
        self.assertNotIn('data-fr27-type="meta status-label"', combined)

    def test_no_stylesheet_consumes_the_semantic_attribute(self):
        styled_sources = list(ROOT.rglob("*.css")) + [INDEX]
        selector = re.compile(r"\[[^\]]*data-fr27-type[^\]]*\]")
        for path in styled_sources:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertIsNone(
                    selector.search(path.read_text(encoding="utf-8")),
                )


if __name__ == "__main__":
    unittest.main()
