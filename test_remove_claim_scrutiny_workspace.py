from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
HYBRID = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")
HYBRID_CSS = (ROOT / "assets" / "hybrid-dashboard.css").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
CANDIDATE_WORKSPACE = (
    ROOT / "assets" / "candidate-signals-workspace.js"
).read_text(encoding="utf-8")

def views_block():
    start = HYBRID.index("  const views = Object.freeze({")
    end = HYBRID.index("  const viewOrder = Object.keys(views);", start)
    return HYBRID[start:end]

def focus_workspace_block():
    start = HYBRID.index("  function renderFocusWorkspace(models)")
    end = HYBRID.index("  function resolveCandidateSignalsPortrait(", start)
    return HYBRID[start:end]

def interactions_block():
    start = HYBRID.index("  function bindInteractions()")
    end = HYBRID.index("  function topMediaComparisonPresentation(", start)
    return HYBRID[start:end]

class RemoveClaimScrutinyWorkspaceTests(unittest.TestCase):
    def test_exactly_five_primary_views_remain_in_required_order(self):
        keys = re.findall(
            r"^    ([A-Za-z][A-Za-z0-9]*): \{$",
            views_block(),
            re.MULTILINE,
        )
        self.assertEqual(
            keys,
            ["candidates", "runoff", "events", "agenda", "issues"],
        )

    def test_claims_is_absent_from_view_registry_and_surface(self):
        block = views_block()
        self.assertNotIn("claims:", block)
        self.assertNotIn("#signal-claims", block)
        self.assertNotIn("signal-claims-tab", HYBRID)
        self.assertNotIn('id="signal-claims-panel"', HYBRID)
        self.assertNotIn('id="signal-claims-panel"', INDEX)

    def test_candidates_default_and_obsolete_hash_fallback_contract(self):
        self.assertIn('const defaultView = "candidates";', HYBRID)
        start = HYBRID.index("  function resolveSignalViewFromHash()")
        end = HYBRID.index("  function renderAll(", start)
        resolver = HYBRID[start:end]
        self.assertIn("hashToView.get(window.location.hash)", resolver)
        self.assertIn("window.history.replaceState(", resolver)
        self.assertIn("views[defaultView].hash", resolver)
        self.assertIn("return defaultView;", resolver)

    def test_focus_workspace_has_no_claims_panel(self):
        block = focus_workspace_block()
        self.assertNotIn("renderClaimsPanel(", block)
        self.assertNotIn("models.claims", block)
        for required in (
            'id="signal-candidates-panel"',
            'id="signal-runoff-panel"',
            'id="signal-events-panel"',
            'id="signal-agenda-panel"',
            'id="signal-issues-panel"',
        ):
            self.assertIn(required, block)

    def test_five_tabs_share_row_evenly(self):
        self.assertIn(
            "WORKSPACE NAVIGATION — LOCKED CONTRACT",
            HYBRID_CSS,
        )
        self.assertIn(
            "flex: 1 1 0 !important;",
            HYBRID_CSS,
        )
        self.assertNotIn(
            'data-hybrid-view="claims"',
            HYBRID_CSS,
        )

    def test_tab_aria_and_keyboard_contract_remains(self):
        for required in (
            'role="tablist"',
            'role="tab"',
            'aria-controls="${views[key].panelId}"',
            'aria-selected="${String(state.activeView === key)}"',
            'tabindex="${state.activeView === key ? "0" : "-1"}"',
        ):
            self.assertIn(required, HYBRID)
        block = interactions_block()
        for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
            self.assertIn(f'event.key === "{key}"', block)
        self.assertIn("tabs.length", block)

    def test_no_orphan_global_claims_state_handlers_or_renderers(self):
        for removed in (
            "claimsRelationship",
            "claimsCandidateId",
            "claimsPublisher",
            "data-hybrid-claims-relationship",
            "data-hybrid-claims-candidate",
            "data-hybrid-claims-publisher",
            "function filteredClaimReviews(",
            "function renderClaimRows(",
            "function renderClaimsPanel(",
            "function buildClaimsViewModel(",
            "function renderClaimsSummary(",
        ):
            self.assertNotIn(removed, HYBRID)

    def test_candidate_scrutiny_popover_still_consumes_claims(self):
        for required in (
            "dashboardState.claims",
            "function candidateScrutinyReviewEntries(",
            "function candidateScrutinyDetailState(",
            "function candidateScrutinyReviewRow(",
            "function openCandidateScrutinyPopover(",
            "safeSourceUrl(review.review_url)",
            "item?.candidate_id",
            "candidate.candidate_id",
            "relationship.toUpperCase()",
            "NO PUBLISHED REVIEWS",
            "DETAIL UNAVAILABLE",
        ):
            self.assertIn(required, HYBRID)

    def test_candidate_dossier_scrutiny_remains(self):
        for required in (
            "function scrutinySummaryCard(",
            '"SCRUTINY"',
            "candidate.scrutiny",
            '"ABOUT"',
            '"BY"',
            '"ARCHIVE"',
        ):
            self.assertIn(required, CANDIDATE_WORKSPACE)

    def test_signal_desk_fact_checks_and_claim_loader_remain(self):
        for required in (
            "function renderFactChecks()",
            "function claimReviewRow(",
            "function renderClaimWire()",
            "function validateClaimsPayload(",
            'fetch("claims_under_scrutiny.json"',
            'markDataset("claims", "loaded", claimsPayload',
            'markDataset("claims", "error")',
        ):
            self.assertIn(required, INDEX)

    def test_dashboard_claims_remains_available(self):
        self.assertIn("dashboardState.claims", HYBRID)
        self.assertIn('markDataset("claims", "loaded", claimsPayload', INDEX)

if __name__ == "__main__":
    unittest.main()
