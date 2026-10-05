"""Phase 2B shared styling and unchanged Media data contracts.

Behavior, focus, route census, fault states and geometry are exercised by
tools/responsive-forensics/tests/menu-footer-polish.mjs.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent


class MenuFooterPolishContracts(unittest.TestCase):
    def test_launcher_persistent_and_pointer_states_preserve_host_geometry(self):
        css = (ROOT / 'assets/fr27-section-launcher.css').read_text(encoding='utf8')
        trigger = re.search(r'\[data-fr27-section-launcher\] \.fr27-section-launcher-trigger \{([^}]+)', css).group(1)
        for property_name in ('border-color:', 'background:', 'box-shadow:', 'cursor: pointer'):
            self.assertIn(property_name, trigger)
        self.assertNotRegex(trigger, r'(?<![-\w])(?:width|height|border-width):')
        self.assertIn('@media (hover: hover)', css)
        self.assertIn('.fr27-section-launcher-trigger:hover', css)
        self.assertIn('.fr27-section-launcher-trigger[aria-expanded="true"] {', css)

    def test_launcher_retains_non_color_open_and_focus_semantics(self):
        css = (ROOT / 'assets/fr27-section-launcher.css').read_text(encoding='utf8')
        self.assertIn('transform: rotate(225deg)', css)
        self.assertIn('border-right: 2px solid currentColor', css)
        self.assertIn(':focus-visible', css)
        self.assertIn('outline: 2px solid var(--final-cyan)', css)
        self.assertIn('grid-template-columns: repeat(2, minmax(0, 1fr))', css)
        self.assertIn('@media (prefers-reduced-motion: reduce)', css)

    def test_shared_layer_owns_escape_only_when_a_popup_is_open(self):
        js = (ROOT / 'assets/fr27-ui.js').read_text(encoding='utf8')
        handler = js.split('document.addEventListener("keydown", event => {')[1].split('\n  });')[0]
        self.assertIn('if (!activeTrigger && !note) return;', handler)
        self.assertIn('event.preventDefault();', handler)
        self.assertIn('event.stopPropagation();', handler)
        self.assertNotIn('event.stopImmediatePropagation();', handler)
        self.assertNotIn('.blur()', handler)
        self.assertIn('hide();', handler)
        self.assertIn('note.classList.add("is-dismissed")', handler)

    def test_custom_notes_dismiss_in_shared_layer_without_family_geometry(self):
        js = (ROOT / 'assets/fr27-ui.js').read_text(encoding='utf8')
        css = (ROOT / 'assets/fr27-ui.css').read_text(encoding='utf8')
        self.assertIn('.issue-note-tooltip, .agenda-note-tooltip', js)
        self.assertIn('document.addEventListener("pointerover", reopenNote)', js)
        self.assertIn('document.addEventListener("focusin", reopenNote)', js)
        self.assertRegex(css, r'\.is-dismissed\s+:is\(.+?\) \{\s+visibility: hidden !important;\s+opacity: 0 !important;\s+\}')

    def test_agenda_target_listener_releases_escape_after_dismissal(self):
        js = (ROOT / 'assets/agenda.js').read_text(encoding='utf8')
        self.assertIn('event.key === "Escape" && !note.classList.contains("is-dismissed")', js)

    def test_status_is_out_of_flow_and_empty_is_zero(self):
        css = (ROOT / 'assets/final-dashboard-shell.css').read_text(encoding='utf8')
        status = css.split('.dashboard-refresh-status {')[1].split('}')[0]
        self.assertIn('position: absolute;', status)
        self.assertNotIn('min-height:', status)
        self.assertIn('.dashboard-refresh-status:empty { height: 0; padding: 0; }', css)
        for file in ('index.html', 'en/index.html'):
            html = (ROOT / file).read_text(encoding='utf8')
            for id in ('what-changed-status', 'top-media-pulse-status'):
                self.assertRegex(html, rf'id="{id}"[^>]*role="status"[^>]*aria-live="polite"')

    def test_candidate_leaders_keep_model_cap_and_scroll_reachability(self):
        js = (ROOT / 'assets/hybrid-dashboard.js').read_text(encoding='utf8')
        css = (ROOT / 'assets/final-dashboard-shell.css').read_text(encoding='utf8')
        self.assertIn('candidateCoverageLeaders = candidateCoverageShares.slice(0, 6)', js)
        final_list = css.rsplit('.top-media-pulse #top-media-overview-panel .top-media-shift-list {', 1)[1].split('}')[0]
        self.assertIn('overflow-y: auto !important', final_list)
        self.assertIn('grid-auto-rows: 22px', final_list)
        self.assertIn('.top-media-shift-row:nth-child(n)', css)


if __name__ == '__main__':
    unittest.main()
