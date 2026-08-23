from pathlib import Path
import json
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent
WORKSPACE = (ROOT / "assets" / "candidate-signals-workspace.js").read_text(encoding="utf-8")
HYBRID = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "candidate-signals.css").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def run_detail_state(load_state, reviews):
    script = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const source = fs.readFileSync("assets/hybrid-dashboard.js", "utf8");
const start = source.indexOf("  function candidateScrutinyCompareText(");
const end = source.indexOf("  function candidateScrutinyNode(", start);
if (start < 0 || end < 0) throw new Error("scrutiny pure-function block missing");
const dashboardState = {
  loadState: { claims: input.loadState },
  claims: input.claims
};
const context = { dashboardState, String, Array, Object };
vm.runInNewContext(source.slice(start, end), context);
const candidate = {
  candidate_id: "alpha",
  candidate_name: "Alpha Candidate"
};
const detail = context.candidateScrutinyDetailState(candidate);
process.stdout.write(JSON.stringify({
  state: detail.state,
  ids: detail.reviews.map(item => item.review.id),
  relationships: detail.reviews.map(item => item.relationship),
  claims: detail.reviews.map(item => item.review.claim_text),
  ratings: detail.reviews.map(item => item.review.rating),
  publishers: detail.reviews.map(item => item.review.publisher_name),
  urls: detail.reviews.map(item => item.review.review_url)
}));
"""
    payload = {
        "loadState": load_state,
        "claims": None if reviews is None else {"reviews": reviews},
    }
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        input=json.dumps(payload),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def sample_reviews():
    return [
        {
            "id": "zeta",
            "review_date": "2026-08-15",
            "publisher_name": "Zeta",
            "claim_text": "Texte Z",
            "rating": "Plutôt faux",
            "review_url": "https://example.test/z",
            "candidate_associations": [
                {"candidate_id": "alpha", "relationship": "about"}
            ],
        },
        {
            "id": "alpha",
            "review_date": "2026-08-15",
            "publisher_name": "Alpha",
            "claim_text": "Texte A",
            "rating": "Vrai",
            "review_url": "https://example.test/a",
            "candidate_associations": [
                {"candidate_id": "alpha", "relationship": "by"}
            ],
        },
        {
            "id": "old",
            "review_date": "2026-08-14",
            "publisher_name": "Beta",
            "claim_text": "Ancien",
            "rating": "Faux",
            "review_url": "https://example.test/old",
            "candidate_associations": [
                {"candidate_id": "alpha", "relationship": "about"}
            ],
        },
        {
            "id": "unrelated",
            "review_date": "2026-08-20",
            "publisher_name": "Other",
            "claim_text": "DO NOT RENDER",
            "rating": "Faux",
            "review_url": "https://example.test/other",
            "candidate_associations": [
                {"candidate_id": "beta", "relationship": "by"}
            ],
        },
    ]


class CandidateScrutinyPopoverTests(unittest.TestCase):
    def test_four_card_contract_and_summary_renderer_remain(self):
        selected_start = WORKSPACE.index("  function selectedAnalysis(")
        selected_end = WORKSPACE.index("  function dossierMetric(", selected_start)
        selected = WORKSPACE[selected_start:selected_end]
        self.assertIn("pollSummaryCard(candidate, metadata)", selected)
        self.assertIn("attentionSummaryCard(", selected)
        self.assertIn("scopeCompositionCard(candidate)", selected)
        self.assertIn("scrutinySummaryCard(candidate, onOpenScrutiny)", selected)
        for locked in (
            '"ABOUT"',
            '"BY"',
            '"REVIEWS"',
            '"14 DAYS"',
            '"ARCHIVE"',
            "`LATEST REVIEW · ${formatDisplayDate(newestDate)}`",
        ):
            self.assertIn(locked, WORKSPACE)

    def test_card_accessibility_and_activation_contract(self):
        start = WORKSPACE.index("  function scrutinySummaryCard(")
        end = WORKSPACE.index("  function evidenceStructureStat(", start)
        card = WORKSPACE[start:end]
        for required in (
            '"div"',
            'card.setAttribute("role", "button")',
            'card.setAttribute("tabindex", "0")',
            'card.setAttribute("aria-haspopup", "dialog")',
            'card.setAttribute("aria-expanded", "false")',
            "candidate.candidate_name",
            'card.addEventListener("click", openScrutiny)',
            'event.key !== "Enter" && event.key !== " "',
            "onOpenScrutiny(candidate, card)",
        ):
            self.assertIn(required, card)

    def test_exact_id_filter_sort_relationships_and_fields(self):
        result = run_detail_state("loaded", sample_reviews())
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["ids"], ["alpha", "zeta", "old"])
        self.assertEqual(result["relationships"], ["by", "about", "about"])
        self.assertNotIn("DO NOT RENDER", result["claims"])
        self.assertEqual(result["publishers"], ["Alpha", "Zeta", "Beta"])
        self.assertEqual(result["ratings"], ["Vrai", "Plutôt faux", "Faux"])
        self.assertTrue(all(url.startswith("https://") for url in result["urls"]))

    def test_no_review_loading_and_unavailable_are_distinct(self):
        self.assertEqual(run_detail_state("loaded", [])["state"], "ready")
        self.assertEqual(run_detail_state("loading", [])["state"], "loading")
        self.assertEqual(run_detail_state("error", None)["state"], "unavailable")
        for required in (
            "NO PUBLISHED REVIEWS",
            "No monitored publisher review is currently associated with this candidate.",
            "DETAIL UNAVAILABLE",
            "Candidate scrutiny summary remains available.",
            "Detailed publisher reviews could not be loaded.",
            "Loading monitored publisher reviews",
            "skeletonElement",
        ):
            self.assertIn(required, HYBRID)

    def test_row_renderer_uses_publisher_text_rating_and_safe_source_policy(self):
        row_start = HYBRID.index("  function candidateScrutinyReviewRow(")
        row_end = HYBRID.index("  function candidateScrutinyBody(", row_start)
        row = HYBRID[row_start:row_end]
        for required in (
            "review.review_date",
            "review.publisher_name",
            "review.claim_text",
            "review.rating",
            "safeSourceUrl(review.review_url)",
            '"OPEN SOURCE ↗"',
            'link.target = "_blank"',
            'link.rel = "noopener noreferrer"',
            '"SOURCE UNAVAILABLE"',
        ):
            self.assertIn(required, row)

    def test_relationship_disclosure_is_locked(self):
        self.assertIn(
            "BY — candidate is the recorded claimant. ABOUT — candidate is mentioned in a checked claim attributed to somebody else.",
            HYBRID,
        )

    def test_dialog_lifecycle_contract(self):
        for required in (
            'panel.setAttribute(\n      "role",\n      "dialog"',
            'panel.setAttribute(\n      "aria-modal",\n      "false"',
            'anchorElement.setAttribute(\n      "aria-expanded",\n      "true"',
            'active.anchor?.setAttribute(\n      "aria-expanded",\n      "false"',
            'document.addEventListener(\n      "pointerdown"',
            'event.key !== "Escape"',
            'close.addEventListener(\n      "click"',
            "panel.contains(event.target)",
            "anchorElement.contains(",
            "active.anchor.focus()",
            'closeCandidateScrutinyPopover({\n      restoreFocus: false\n    });',
        ):
            self.assertIn(required, HYBRID)

    def test_only_one_and_rerender_cleanup_contract(self):
        open_start = HYBRID.index("  function openCandidateScrutinyPopover(")
        open_end = HYBRID.index("  function renderCandidateSignalsPanel()", open_start)
        open_block = HYBRID[open_start:open_end]
        self.assertIn(
            'closeCandidateScrutinyPopover({\n      restoreFocus: false\n    });',
            open_block,
        )
        render_start = HYBRID.index("  function renderCandidateSignalsPanel()")
        render_end = HYBRID.index("  function setActiveSignalView(", render_start)
        renderer = HYBRID[render_start:render_end]
        self.assertIn(
            'closeCandidateScrutinyPopover({\n      restoreFocus: false\n    });',
            renderer,
        )
        self.assertIn("onOpenScrutiny(", renderer)
        self.assertIn("openCandidateScrutinyPopover(", renderer)

    def test_positioning_and_mobile_sheet_contract(self):
        for required in (
            "window.innerWidth",
            "window.innerHeight",
            "anchor.getBoundingClientRect()",
            "panel.getBoundingClientRect()",
            '"(max-width: 640px)"',
            'panel.classList.toggle(\n      "is-sheet"',
            "width: min(440px, calc(100vw - 24px));",
            "max-height: min(72vh, 640px);",
            "@media (max-width: 640px)",
            ".candidate-signals-scrutiny-popover.is-sheet",
        ):
            self.assertIn(required, HYBRID + CSS)

    def test_global_claim_workspace_is_removed_while_signal_desk_fact_checks_remain(self):
        for removed in (
            'id="signal-claims-panel"',
            "function renderClaimsPanel(",
            "function buildClaimsViewModel(",
        ):
            self.assertNotIn(removed, HYBRID)
        for required in (
            "function renderFactChecks()",
            "function claimReviewRow(",
            "function renderClaimWire()",
        ):
            self.assertIn(required, INDEX)


if __name__ == "__main__":
    unittest.main()
