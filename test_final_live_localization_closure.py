from pathlib import Path
import json
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
HYBRID = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")
CANDIDATE_WORKSPACE = (
    ROOT / "assets" / "candidate-signals-workspace.js"
).read_text(encoding="utf-8")


def catalog(path: str) -> dict[str, str]:
    source = (ROOT / path).read_text(encoding="utf-8")
    match = re.search(
        r"const messages = Object\.freeze\((\{.*?\})\);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"Localization catalog missing from {path}")
    return json.loads(match.group(1))


EN = catalog("locales/en.js")
FR = catalog("locales/fr.js")


MASTHEAD_RUNTIME = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const index = fs.readFileSync("index.html", "utf8");
const start = index.indexOf("    function dashboardTimestamp(value)");
const end = index.indexOf("\n    function pollFieldworkLabel(event)", start);
if (start < 0 || end < 0) throw new Error("masthead helper block not found");

const catalogSource = fs.readFileSync(`locales/${input.locale}.js`, "utf8");
const catalogMatch = catalogSource.match(
  /const messages = Object\.freeze\((\{[\s\S]*?\})\);/
);
const messages = JSON.parse(catalogMatch[1]);
const localeTag = input.locale === "fr" ? "fr-FR" : "en-GB";
const attributes = new Map();
const countdown = {
  setAttribute(name, value) { attributes.set(name, String(value)); },
  removeAttribute(name) { attributes.delete(name); }
};
const interpolate = (message, parameters = {}) => String(message).replace(
  /\{([A-Za-z0-9_]+)\}/g,
  (match, name) => Object.prototype.hasOwnProperty.call(parameters, name)
    ? String(parameters[name])
    : match
);
const context = {
  Intl,
  Date,
  Number,
  Object,
  String,
  FR27I18N: {
    locale: input.locale,
    localeTag,
    t(key, parameters, fallback) {
      return interpolate(messages[key] || fallback || key, parameters || {});
    }
  },
  translate(key, fallback, parameters) {
    return interpolate(messages[key] || fallback || key, parameters || {});
  },
  dashboardState: {
    manifest: null,
    loadState: { manifest: "loading" }
  },
  $(selector) { return selector === "#masthead-countdown" ? countdown : null; }
};
vm.createContext(context);
vm.runInContext(index.slice(start, end), context);

const manifest = {
  published_at: "2026-09-08T12:32:00Z",
  lanes: {
    polls: {
      available: true,
      valid: true,
      timestamp_status: "known",
      last_success_at: "2026-09-08T12:32:00Z"
    },
    runoff: { available: true, valid: true, data_as_of: "2026-09-08" },
    news: {
      available: true,
      valid: true,
      timestamp_status: "known",
      generated_at: "2026-09-08T12:32:00Z"
    },
    claims: { available: true, valid: true, data_as_of: "2026-09-08" },
    recent_changes: {
      available: true,
      valid: true,
      timestamp_status: "known",
      last_success_at: "2026-09-08T12:32:00Z"
    }
  }
};

context.renderMastheadMetadata();
const loading = attributes.get("data-fr27-tooltip");
context.dashboardState.manifest = manifest;
context.dashboardState.loadState.manifest = "loaded";
context.renderMastheadMetadata();

process.stdout.write(JSON.stringify({
  loading,
  tooltip: attributes.get("data-fr27-tooltip"),
  dateTime: context.formatMastheadParisDateTime(manifest.published_at),
  clock: context.formatMastheadParisClock(manifest.published_at),
  evidenceDate: context.formatManifestEvidenceDate("2026-09-08"),
  unavailable: context.unavailableLaneLabel("news", null),
  invalid: context.unavailableLaneLabel(
    "claims",
    { valid: false, timestamp_status: "invalid" }
  ),
  unknown: context.unavailableLaneLabel(
    "recent_changes",
    { valid: true, timestamp_status: "unknown" }
  ),
  rawLaneIds: Object.keys(manifest.lanes)
}));
"""


def masthead_runtime(locale: str) -> dict:
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("Node.js is required for masthead runtime checks")
    result = subprocess.run(
        [node, "-e", MASTHEAD_RUNTIME],
        input=json.dumps({"locale": locale}),
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class FinalLiveLocalizationClosureTests(unittest.TestCase):
    def test_about_popover_is_reachable_and_contains_approved_copy(self):
        toggle = re.search(
            r'<button\s+[^>]*id="fr27-hud-info-toggle"[\s\S]*?</button>',
            INDEX,
        ).group(0)
        popover = re.search(
            r'<aside\s+[^>]*id="fr27-hud-info-popover"[\s\S]*?</aside>',
            INDEX,
        ).group(0)

        self.assertIn('aria-controls="fr27-hud-info-popover"', toggle)
        self.assertIn('aria-expanded="false"', toggle)
        self.assertIn('aria-hidden="true"', popover)
        self.assertIn("infoToggle.addEventListener(", INDEX)
        self.assertIn("setInfoOpen(!open);", INDEX)
        self.assertIn('data-i18n="hud.rights_licences"', popover)
        self.assertEqual(EN["hud.rights_licences"], "RIGHTS & LICENCES")
        self.assertEqual(FR["hud.rights_licences"], "DROITS & LICENCES")
        self.assertEqual(
            EN["hud.licence_summary"],
            "POLYFORM NC · CC BY-NC 4.0",
        )
        self.assertEqual(EN["hud.licence_summary"], FR["hud.licence_summary"])
        self.assertEqual(EN["hud.licence_details"], "DETAILS ↗")
        self.assertEqual(FR["hud.licence_details"], "DÉTAILS ↗")
        self.assertIn(
            'href="https://github.com/openeventbits/'
            'france-2027-signal-lab/blob/main/NOTICE"',
            popover,
        )
        self.assertIn('target="_blank"', popover)
        self.assertIn('rel="noopener noreferrer"', popover)
        self.assertIn('data-i18n-aria-label="hud.open_licensing_notice"', popover)

    def test_about_independence_and_portrait_disclosure_are_localized(self):
        self.assertEqual(
            EN["hud.independence_statement"],
            "Independent project · no affiliation with the candidates, parties, "
            "pollsters, publishers or public authorities monitored.",
        )
        self.assertEqual(
            FR["hud.independence_statement"],
            "Projet indépendant · aucune affiliation avec les candidats, partis, "
            "instituts de sondage, médias ou autorités publiques suivis.",
        )
        self.assertEqual(
            EN["hud.ai_portraits_note"],
            "Candidate portraits are AI-generated illustrations for visual identification.",
        )
        self.assertEqual(
            FR["hud.ai_portraits_note"],
            "Les portraits des candidats sont des illustrations générées par IA "
            "destinées à leur identification visuelle.",
        )

    def test_masthead_freshness_is_catalog_owned_with_correct_time_zones(self):
        masthead = INDEX[
            INDEX.index("    function formatMastheadParisDateTime") :
            INDEX.index("\n    function pollFieldworkLabel")
        ]
        self.assertIn("masthead_freshness.loading", masthead)
        self.assertIn("masthead_freshness.snapshot_published", masthead)
        self.assertIn("globalThis.FR27I18N?.localeTag", masthead)
        self.assertNotIn('new Intl.DateTimeFormat("en-GB"', masthead)
        self.assertIn('timeZone: "Europe/Paris"', masthead)
        evidence = masthead[
            masthead.index("function formatManifestEvidenceDate") :
            masthead.index("function mastheadLaneLabel")
        ]
        self.assertIn('timeZone: "UTC"', evidence)
        self.assertNotIn("replace(\",\"", masthead)

        french = masthead_runtime("fr")
        self.assertEqual(
            french["loading"],
            "Chargement de l’instantané de publication et de la fraîcheur des données",
        )
        self.assertEqual(french["dateTime"], "8 sept. 2026 · 14:32 Paris")
        self.assertEqual(french["clock"], "8 sept. · 14:32")
        self.assertEqual(french["evidenceDate"], "8 sept.")
        self.assertIn("Instantané publié · 8 sept. 2026 · 14:32 Paris", french["tooltip"])
        self.assertIn("Sondages vérifiés · 8 sept. · 14:32", french["tooltip"])
        self.assertIn("2e tour · données au 8 sept.", french["tooltip"])
        self.assertIn("Actualités mises à jour · 8 sept. · 14:32", french["tooltip"])
        self.assertIn("Vérifications · données au 8 sept.", french["tooltip"])
        self.assertIn("Changements vérifiés · 8 sept. · 14:32", french["tooltip"])
        self.assertEqual(french["unavailable"], "Actualités · données indisponibles")
        self.assertEqual(french["invalid"], "Vérifications · données invalides")
        self.assertEqual(french["unknown"], "Changements · horaire inconnu")
        self.assertEqual(
            french["rawLaneIds"],
            ["polls", "runoff", "news", "claims", "recent_changes"],
        )

        english = masthead_runtime("en")
        self.assertEqual(english["loading"], "Loading snapshot and evidence freshness")
        self.assertEqual(english["dateTime"], "8 Sept 2026 · 14:32 Paris")
        self.assertEqual(english["clock"], "8 Sept · 14:32")
        self.assertEqual(english["evidenceDate"], "8 Sept")
        self.assertIn("Snapshot published 8 Sept 2026 · 14:32 Paris", english["tooltip"])
        self.assertEqual(english["unavailable"], "News unavailable")
        self.assertEqual(english["invalid"], "Claims invalid")
        self.assertEqual(english["unknown"], "Changes time unknown")

    def test_candidacy_summaries_require_explicit_record_identity(self):
        mapping_match = re.search(
            r"const candidacySummaryKeysByRecordIdentity = Object\.freeze\((\{.*?\})\);",
            CANDIDATE_WORKSPACE,
            re.DOTALL,
        )
        identities = json.loads(mapping_match.group(1))
        self.assertEqual(len(identities), 9)
        self.assertEqual(
            identities["marine-le-pen|declared|2026-07-07"],
            "candidate.candidacy_summary.marine-le-pen",
        )
        for identity, key in identities.items():
            self.assertRegex(identity, r"^[a-z0-9-]+\|[a-z_]+\|\d{4}-\d{2}-\d{2}$")
            self.assertIn(key, EN)
            self.assertIn(key, FR)

        self.assertIn(
            "return candidacySummaryKeysByRecordIdentity[recordIdentity] || \"\";",
            CANDIDATE_WORKSPACE,
        )
        self.assertIn(
            "return key ? translate(key, fallback) : fallback;",
            CANDIDATE_WORKSPACE,
        )
        self.assertIn(
            "const fallback = candidate?.candidacy?.status_note || MISSING;",
            CANDIDATE_WORKSPACE,
        )
        self.assertNotIn("wikipediaCandidacySummaryKeysByStatus", CANDIDATE_WORKSPACE)
        self.assertNotIn('source.hostname === "fr.wikipedia.org"', CANDIDATE_WORKSPACE)
        self.assertFalse(any("candidacy_summary.wikipedia" in key for key in EN))
        self.assertFalse(any("candidacy_summary.wikipedia" in key for key in FR))

        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("Node.js is required for candidacy runtime checks")
        runtime = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("assets/candidate-signals-workspace.js", "utf8");
const start = source.indexOf("  const candidacySummaryKeysByRecordIdentity");
const end = source.indexOf("\n  function counted(value, kind)", start);
if (start < 0 || end < 0) throw new Error("candidacy helper block not found");
const context = {
  Object,
  MISSING: "—",
  translate(key, fallback) { return `localized:${key}:${fallback}`; }
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const unknown = {
  candidate_id: "future-candidate",
  candidacy: {
    status: "declared",
    source_date: "2030-01-02",
    source_url: "https://fr.wikipedia.org/w/index.php?title=Future",
    status_note: "Future record wording must remain verbatim."
  }
};
const known = {
  candidate_id: "marine-le-pen",
  candidacy: {
    status: "declared",
    source_date: "2026-07-07",
    status_note: "Known fallback."
  }
};
process.stdout.write(JSON.stringify({
  unknown: vm.runInContext("candidacyStatusNote", context)(unknown),
  known: vm.runInContext("candidacyStatusNote", context)(known)
}));
"""
        result = subprocess.run(
            [node, "-e", runtime],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        rendered = json.loads(result.stdout)
        self.assertEqual(
            rendered["unknown"],
            "Future record wording must remain verbatim.",
        )
        self.assertTrue(
            rendered["known"].startswith(
                "localized:candidate.candidacy_summary.marine-le-pen:"
            )
        )

    def test_candidate_agenda_profiles_are_fully_locale_owned(self):
        current_start = CANDIDATE_WORKSPACE.index(
            "  function currentAgendaSummaryCard(candidate)"
        )
        historical_start = CANDIDATE_WORKSPACE.index(
            "  function historicalAgendaSummaryCard("
        )
        next_start = CANDIDATE_WORKSPACE.index(
            "\n  function ",
            historical_start + 10,
        )

        current = CANDIDATE_WORKSPACE[current_start:historical_start]
        historical = CANDIDATE_WORKSPACE[historical_start:next_start]

        for key in (
            "candidate.agenda_profile.mode_policy",
            "candidate.agenda_profile.mode_campaign",
            "candidate.agenda_profile.metadata",
            "candidate.agenda_profile.policy_semantics",
            "candidate.agenda_profile.campaign_semantics",
        ):
            self.assertIn(key, CANDIDATE_WORKSPACE)
            self.assertIn(key, EN)
            self.assertIn(key, FR)

        for key in (
            "candidate.agenda_profile.cumulative_metadata",
            "candidate.agenda_profile.unavailable_cumulative",
            "candidate.agenda_profile.empty_current",
            "candidate.agenda_profile.empty_since_tracking",
        ):
            self.assertIn(key, CANDIDATE_WORKSPACE)
            self.assertIn(key, EN)
            self.assertIn(key, FR)

        self.assertNotIn('? "POLICY"', historical)
        self.assertNotIn(': "CAMPAIGN"', historical)
        self.assertNotIn(" LINKS · ${period}", historical)
        self.assertNotIn("Cumulative Agenda Profile since ${", historical)
        self.assertIn(
            'translate(\n      "candidate.agenda_profile.unavailable_cumulative"',
            historical,
        )
        self.assertNotIn(
            'const unavailableMessage =\n      "Cumulative Agenda Profile is unavailable',
            historical,
        )

        self.assertIn(
            'translate(\n          "candidate.agenda_profile.empty_since_tracking"',
            historical,
        )
        self.assertNotIn(
            'emptyMessage:\n          "No classified topic coverage since tracking began."',
            historical,
        )

        self.assertIn(
            'translate(\n          "candidate.agenda_profile.empty_current"',
            current,
        )
        self.assertNotIn(
            'emptyMessage:\n          "No classified topic coverage in the current 30-day window."',
            current,
        )

        self.assertEqual(FR["candidate.agenda_profile.mode_policy"], "ENJEUX")
        self.assertEqual(FR["candidate.agenda_profile.mode_campaign"], "CAMPAGNE")
        self.assertIn(
            "{count} ASSOCIATIONS",
            FR["candidate.agenda_profile.cumulative_metadata"],
        )
        self.assertIn(
            "Profil thématique cumulé",
            FR["candidate.agenda_profile.cumulative_metadata"],
        )

        self.assertIn(
            'data-i18n-aria-label="dashboard.loading_candidate_scores"',
            INDEX,
        )
        self.assertEqual(
            FR["dashboard.loading_candidate_scores"],
            "Chargement des scores des candidats…",
        )

    def test_legacy_comparison_and_polling_experiment_are_unreachable(self):
        legacy = re.search(
            r'<section class="intelligence-grid"[^>]+>',
            INDEX,
        ).group(0)
        polling = re.search(
            r'<section class="panel polling-evidence" '
            r'id="polling-evidence-lab"[^>]+>',
            INDEX,
        ).group(0)
        self.assertIn(" hidden", legacy)
        self.assertIn('aria-hidden="true"', legacy)
        self.assertRegex(
            INDEX,
            r"\.intelligence-grid\[hidden\]\s*\{\s*display:\s*none\s*!important;\s*\}",
        )
        self.assertNotIn("retainLegacyComparison", HYBRID)
        self.assertNotIn("Legacy middle layout — comparison only", HYBRID)
        self.assertIn(" hidden", polling)
        self.assertIn('aria-hidden="true"', polling)

    def test_all_five_hybrid_workspaces_remain_mounted(self):
        for workspace in ("candidates", "agenda", "events", "issues", "runoff"):
            with self.subTest(workspace=workspace):
                self.assertIn(f'hash: "#signal-{workspace}"', HYBRID)
                self.assertIn(f'id="signal-{workspace}-panel"', HYBRID)
                self.assertIn(f'tabId: "signal-{workspace}-tab"', HYBRID)

    def test_legal_files_generated_data_and_pipelines_are_untouched(self):
        changed = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        protected_legal = {
            "LICENSE",
            "NOTICE",
            "CONTENT_LICENSE.md",
            "THIRD_PARTY_NOTICES.md",
        }
        self.assertTrue(protected_legal.isdisjoint(changed))
        self.assertFalse(any(path.endswith(".json") for path in changed))
        self.assertFalse(
            any(
                (path.startswith("build_") or path.startswith("fetch_"))
                and path.endswith(".py")
                for path in changed
            )
        )


if __name__ == "__main__":
    unittest.main()
