from pathlib import Path
import json
import re
import subprocess
import unittest

from test_candidate_signals_workspace import candidate, payload, run_workspace


ROOT = Path(__file__).resolve().parent
WORKSPACE = (ROOT / "assets" / "candidate-signals-workspace.js").read_text(
    encoding="utf-8"
)
HYBRID = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")


def catalog(locale):
    source = (ROOT / "locales" / f"{locale}.js").read_text(encoding="utf-8")
    match = re.search(
        r"const messages = Object\.freeze\((\{.*?\})\);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"{locale} catalog was not found")
    return json.loads(match.group(1))


POPOVER_ROW_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const source = fs.readFileSync("assets/hybrid-dashboard.js", "utf8");
const start = source.indexOf("  function candidateScrutinyNode(");
const end = source.indexOf("  function closeCandidateScrutinyPopover(", start);

class MiniNode {
  constructor(tagName, text = "") {
    this.tagName = String(tagName).toUpperCase();
    this.className = "";
    this.children = [];
    this.attributes = {};
    this._text = String(text);
    this.href = "";
    this.target = "";
    this.rel = "";
  }
  set textContent(value) {
    this._text = String(value ?? "");
    this.children = [];
  }
  get textContent() {
    return this._text + this.children.map(child => child.textContent).join("");
  }
  append(...nodes) { this.children.push(...nodes.filter(Boolean)); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  matches(selector) {
    return selector.startsWith(".")
      ? this.className.split(/\s+/).includes(selector.slice(1))
      : this.tagName === selector.toUpperCase();
  }
  querySelectorAll(selector) {
    const result = [];
    const visit = node => node.children.forEach(child => {
      if (child.matches(selector)) result.push(child);
      visit(child);
    });
    visit(this);
    return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

const localeTag = input.locale === "fr" ? "fr-FR" : "en-GB";
const pluralPattern =
  /\{([A-Za-z0-9_]+),\s*plural,\s*one\s*\{([^{}]*)\}\s*other\s*\{([^{}]*)\}\s*\}/g;
const translate = (key, fallback, parameters = {}) => {
  const message = input.messages[key] ?? fallback;
  const pluralized = String(message).replace(
    pluralPattern,
    (_match, name, one, other) =>
      new Intl.PluralRules(localeTag).select(Number(parameters[name])) === "one"
        ? one
        : other
  );
  return pluralized.replace(
    /\{([A-Za-z0-9_]+)\}/g,
    (match, name) => Object.prototype.hasOwnProperty.call(parameters, name)
      ? String(parameters[name])
      : match
  );
};
const document = {
  createElement(tagName) { return new MiniNode(tagName); },
  createTextNode(text) { return new MiniNode("#text", text); }
};
const window = {};
const safeSourceUrl = value => String(value || "");
const candidateDisplayDate = value => new Intl.DateTimeFormat(localeTag, {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC"
}).format(new Date(`${value}T00:00:00Z`));
const context = {
  document,
  window,
  translate,
  safeSourceUrl,
  candidateDisplayDate,
  String,
  Intl,
  Date,
  Object,
  Array
};
vm.runInNewContext(source.slice(start, end), context);

const entry = {
  relationship: input.relationship,
  review: input.review
};
const row = context.candidateScrutinyReviewRow(entry);
const body = context.candidateScrutinyBody({ state: "ready", reviews: [entry] });
const relationship = row.querySelector(".candidate-signals-scrutiny-relationship");
const link = row.querySelector(".candidate-signals-scrutiny-source");
process.stdout.write(JSON.stringify({
  bodyText: body.textContent,
  rowText: row.textContent,
  relationshipText: relationship.textContent,
  relationshipClass: relationship.className,
  href: link.href,
  claim: row.querySelector(".candidate-signals-scrutiny-claim").textContent,
  publisher: row.querySelector(".candidate-signals-scrutiny-publisher").textContent,
  rating: row.querySelector(".candidate-signals-scrutiny-rating").textContent
}));
"""


def run_popover_row(locale, relationship="about"):
    review = {
        "id": "review-stable-17",
        "review_date": "2026-09-08",
        "publisher_name": "Le Monde",
        "claim_text": "Texte source — inchangé.",
        "rating": "Plutôt faux",
        "review_url": "https://example.test/reviews/stable-17?ref=source",
    }
    completed = subprocess.run(
        ["node", "-e", POPOVER_ROW_HARNESS],
        cwd=ROOT,
        input=json.dumps(
            {
                "locale": locale,
                "messages": catalog(locale),
                "relationship": relationship,
                "review": review,
            }
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout), review


class BatchCLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        row = candidate(
            "candidate-stable-17",
            "Élodie Source-Name",
            "https://example.test/news/stable-17?utm_source=fixture",
        )
        row["latest_development"]["publisher"] = "The Source Publisher"
        row["latest_development"]["headline"] = (
            "Source Headline: Keep This English Exactly"
        )
        data = payload([row])
        data["featured_polling_package"]["pollster"] = "Institut SourceName"
        cls.en = run_workspace(data, locale="en")
        cls.fr = run_workspace(data, locale="fr")
        cls.en_catalog = catalog("en")
        cls.fr_catalog = catalog("fr")

    def test_french_major_headings_and_core_cards_render(self):
        text = self.fr["text"]
        for expected in (
            "SUIVI DES CANDIDATS",
            "ANALYSE SÉLECTIONNÉE",
            "DOSSIER CANDIDAT",
            "DONNÉES DE SONDAGE",
            "VISIBILITÉ CAMPAGNE",
            "RÉPARTITION DE LA COUVERTURE",
            "VISIBILITÉ & RÉPARTITION",
            "STRUCTURE DES DONNÉES",
            "VÉRIFICATIONS · 14 J",
            "APERÇU DES VÉRIFICATIONS",
            "DERNIÈRE VÉRIFICATION",
            "DERNIÈRE ÉVOLUTION",
            "JOURS ACTIFS",
            "PÉRIODE PUBLIÉE",
            "ÉLÉMENTS PUBLIÉS",
            "SOURCES PUBLIÉES",
            "MÉDIA PRINCIPAL",
            "CONCENTRATION MÉDIAS",
            "CONCENTRATION DES SUJETS",
            "VISIBILITÉ GÉNÉRALE",
            "CAMPAGNE / ÉLECTION",
        ):
            self.assertIn(expected, text)
        self.assertEqual(self.fr["searchPlaceholder"], "Rechercher un candidat…")

    def test_english_candidate_workspace_remains_unchanged(self):
        text = self.en["text"]
        for expected in (
            "CANDIDATE MONITOR",
            "SELECTED ANALYSIS",
            "CANDIDATE DOSSIER",
            "POLL EVIDENCE",
            "CAMPAIGN ATTENTION",
            "RACE COVERAGE MIX",
            "VISIBILITY & COMPOSITION",
            "EVIDENCE STRUCTURE",
            "SCRUTINY · 14 DAYS",
            "SCRUTINY OVERVIEW",
            "LATEST REVIEW",
            "LATEST DEVELOPMENT",
            "ACTIVE DAYS",
            "PUBLISHED RANGE",
            "Top publisher",
            "Top story concentration",
        ):
            self.assertIn(expected, text)
        self.assertIn("Sample1,503", text)
        self.assertIn("29 Jul 2026", text)

    def test_localized_relationship_labels_keep_stable_semantic_identity(self):
        labels = self.fr["dossierScrutinyLabelDetails"]
        self.assertEqual(
            [item["text"] for item in labels],
            ["SUR", "PAR", "VÉRIF.", "SUR", "PAR", "VÉRIF."],
        )
        self.assertTrue(labels[0]["ariaLabel"].startswith("SUR —"))
        self.assertTrue(labels[1]["ariaLabel"].startswith("PAR —"))
        self.assertEqual(self.fr["dossierScrutinyValues"], ["1", "0", "1", "2", "1", "3"])

        start = WORKSPACE.index("  function dossierScrutinyMetric(")
        end = WORKSPACE.index("  function dossierScrutinyPeriod(", start)
        metric = WORKSPACE[start:end]
        self.assertIn("relationshipKind", metric)
        self.assertIn('relationshipKind === "about"', metric)
        self.assertIn('relationshipKind === "by"', metric)
        self.assertNotIn('label === "ABOUT"', metric)
        self.assertNotIn('label === "BY"', metric)

    def test_source_derived_candidate_evidence_and_stable_ids_are_unchanged(self):
        unchanged = (
            "Élodie Source-Name",
            "Institut SourceName",
            "The Source Publisher",
            "Source Headline: Keep This English Exactly",
            "Example",
            "General Example",
        )
        for value in unchanged:
            self.assertIn(value, self.fr["text"])
            self.assertIn(value, self.en["text"])
        self.assertEqual(self.fr["candidateOrder"], ["candidate-stable-17"])
        self.assertEqual(self.fr["candidateOrder"], self.en["candidateOrder"])
        source_url = "https://example.test/news/stable-17?utm_source=fixture"
        self.assertIn(source_url, self.fr["linkHrefs"])
        self.assertEqual(self.fr["linkHrefs"], self.en["linkHrefs"])

    def test_french_candidate_numbers_and_dates_use_locale_formatting(self):
        text = self.fr["text"]
        self.assertIn("Échantillon1\u202f503", text)
        self.assertIn("29 juil. 2026", text)
        self.assertIn("25\u00a0%", text)
        self.assertNotIn("Sample1,503", text)
        self.assertNotIn("29 Jul 2026", text)

    def test_tested_french_fixture_has_no_app_owned_obvious_english(self):
        text = self.fr["text"]
        for english in (
            "CANDIDATE MONITOR",
            "SELECTED ANALYSIS",
            "CANDIDATE DOSSIER",
            "POLL EVIDENCE",
            "CAMPAIGN ATTENTION",
            "RACE COVERAGE MIX",
            "VISIBILITY & COMPOSITION",
            "EVIDENCE STRUCTURE",
            "SCRUTINY OVERVIEW",
            "LATEST REVIEW",
            "LATEST DEVELOPMENT",
            "ACTIVE DAYS",
            "PUBLISHED RANGE",
            "Open source",
            "Search candidate",
            "Not tested",
        ):
            self.assertNotIn(english, text)

    def test_scrutiny_popover_localizes_chrome_and_preserves_source_fields(self):
        about, review = run_popover_row("fr", "about")
        by, _ = run_popover_row("fr", "by")
        self.assertEqual(about["relationshipText"], "SUR")
        self.assertIn("is-about", about["relationshipClass"])
        self.assertEqual(by["relationshipText"], "PAR")
        self.assertIn("is-by", by["relationshipClass"])
        self.assertIn("Ouvrir la source ↗", about["rowText"])
        self.assertIn("8 sept. 2026", about["rowText"])
        self.assertIn("PAR —", about["bodyText"])
        self.assertIn("SUR —", about["bodyText"])
        self.assertEqual(about["claim"], review["claim_text"])
        self.assertEqual(about["publisher"], review["publisher_name"])
        self.assertEqual(about["rating"], review["rating"])
        self.assertEqual(about["href"], review["review_url"])
        self.assertIn('"candidate.claim_scrutiny_title"', HYBRID)
        self.assertIn('"candidate.scrutiny.monitored_review_count"', HYBRID)

    def test_candidate_catalog_additions_are_semantic_and_bilingual(self):
        required = {
            "candidate.candidate_monitor",
            "candidate.selected_analysis",
            "candidate.candidate_dossier",
            "candidate.scrutiny.about_semantics",
            "candidate.scrutiny.by_semantics",
            "candidate.scrutiny.relationship_disclosure",
            "candidate.claim_scrutiny_title",
            "candidate.open_source",
        }
        self.assertTrue(required.issubset(self.en_catalog))
        self.assertTrue(required.issubset(self.fr_catalog))
        for polluted in (
            "candidate.noopener_noreferrer",
            "candidate.candidate_signals_dossier_card_candidate_signals_dossier_scrutiny",
        ):
            self.assertNotIn(polluted, self.fr_catalog)


if __name__ == "__main__":
    unittest.main()
