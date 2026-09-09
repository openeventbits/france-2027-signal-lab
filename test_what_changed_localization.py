import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent


WHAT_CHANGED_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const indexSource = fs.readFileSync("index.html", "utf8").replace(/\r\n/g, "\n");

class Element {
  constructor(tagName = "div", attributes = {}, textContent = "") {
    this.tagName = tagName.toUpperCase();
    this.attributes = new Map(Object.entries(attributes));
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.listeners = new Map();
    this.style = { setProperty() {} };
    this._textContent = String(textContent);
    this.className = "";
    this.tabIndex = -1;
  }
  get textContent() {
    return this._textContent + this.children.map(child => child.textContent).join("");
  }
  set textContent(value) {
    this._textContent = String(value ?? "");
    this.children = [];
  }
  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }
  removeAttribute(name) {
    this.attributes.delete(name);
  }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  append(...children) {
    children.forEach(child => this.appendChild(child));
  }
  replaceChildren(...children) {
    this._textContent = "";
    this.children = [];
    this.append(...children);
  }
  addEventListener(type, callback) {
    const callbacks = this.listeners.get(type) || [];
    callbacks.push(callback);
    this.listeners.set(type, callbacks);
  }
  click() {
    for (const callback of this.listeners.get("click") || []) callback();
  }
  focus() {}
}

const title = new Element("h2", { "data-i18n": "dashboard.what_changed" }, "WHAT CHANGED");
const summary = new Element("div", {
  "data-i18n-aria-label": "what_changed.loading_count",
  "aria-label": "Loading source-linked update count"
});
const list = new Element("div", {
  "data-i18n-aria-label": "what_changed.loading",
  "aria-label": "Loading source-linked dashboard changes"
});
const documentListeners = new Map();

const walk = root => [root, ...root.children.flatMap(walk)];
const byClass = (root, className) => walk(root).filter(node =>
  String(node.className).split(/\s+/).includes(className)
);

const documentObject = {
  documentElement: { dataset: { siteRoot: "./" }, lang: "fr" },
  baseURI: input.href,
  readyState: "loading",
  title: "",
  createElement(tagName) { return new Element(tagName); },
  createElementNS(_namespace, tagName) { return new Element(tagName); },
  querySelectorAll(selector) {
    return {
      "[data-i18n]": [title],
      "[data-i18n-aria-label]": [summary, list],
      "[data-i18n-fr27-tooltip]": [],
      "[data-fr27-language]": []
    }[selector] || [];
  },
  querySelector(selector) {
    const match = selector.match(/^\[data-ledger-filter="([^"]+)"\]$/);
    return match
      ? byClass(list, "changes-ledger-filter").find(
          node => node.dataset.ledgerFilter === match[1]
        ) || null
      : null;
  },
  addEventListener(type, callback) {
    const callbacks = documentListeners.get(type) || [];
    callbacks.push(callback);
    documentListeners.set(type, callbacks);
  }
};

const windowObject = {
  document: documentObject,
  location: new URL(input.href),
  console: { warn() {} },
  addEventListener() {},
  setTimeout(callback) { callback(); return 1; },
  FR27UI: {
    skeletonElement(_kind, label) {
      const element = new Element("div");
      element.setAttribute("aria-label", label);
      return element;
    }
  }
};

const originalPayload = JSON.stringify(input.recentChanges);
const dashboardState = {
  recentChanges: input.recentChanges,
  polls: input.polls,
  claims: input.claims,
  loadState: { recentChanges: input.state }
};
const elements = new Map([
  ["#what-changed-list", list],
  ["#changes-ledger-summary", summary]
]);
const context = {
  window: windowObject,
  globalThis: windowObject,
  document: documentObject,
  URL,
  URLSearchParams,
  Intl,
  Object,
  String,
  Number,
  Boolean,
  Array,
  Math,
  Set,
  Map,
  Date,
  console: windowObject.console,
  dashboardState,
  input,
  title,
  summary,
  list,
  byClass,
  originalPayload,
  fetch() { return new Promise(() => {}); },
  requestAnimationFrame(callback) { callback(); },
  $(selector) { return elements.get(selector) || null; },
  safeSourceUrl(value) {
    try {
      const url = new URL(String(value));
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_error) {
      return "";
    }
  },
  renderInlineSkeleton(target, label) {
    target.replaceChildren(new Element("span"));
    target.setAttribute("aria-busy", "true");
    target.setAttribute("aria-label", label);
  },
  renderResolvedText(target, text) {
    target.textContent = text;
    target.removeAttribute("aria-busy");
    target.removeAttribute("aria-label");
  },
  appendBriefingText(parent, className, text, tagName = "div") {
    const element = new Element(tagName);
    element.className = className;
    element.textContent = text;
    parent.appendChild(element);
    return element;
  },
  result: null
};

vm.runInNewContext(fs.readFileSync("locales/en.js", "utf8"), context);
vm.runInNewContext(fs.readFileSync("locales/fr.js", "utf8"), context);
vm.runInNewContext(fs.readFileSync("assets/localization.js", "utf8"), context);
for (const callback of documentListeners.get("DOMContentLoaded") || []) callback();
context.translate = (key, fallback, parameters) =>
  windowObject.FR27I18N.t(key, parameters, fallback);

const start = indexSource.indexOf("    let whatChangedLedgerFilter = \"all\";");
const end = indexSource.indexOf("    function subtractCalendarMonths", start);
if (start < 0 || end < 0) throw new Error("What Changed renderer slice not found");

vm.runInNewContext(
  indexSource.slice(start, end) + `
ledgerSourceIconState.status = "error";
renderWhatChanged();
const filters = byClass(list, "changes-ledger-filter").map(node => ({
  key: node.dataset.ledgerFilter,
  text: node.textContent,
  pressed: node.getAttribute("aria-pressed")
}));
const campaignFilter = byClass(list, "changes-ledger-filter").find(
  node => node.dataset.ledgerFilter === "campaign"
);
if (input.clickCampaign && campaignFilter) campaignFilter.click();
result = {
  title: title.textContent,
  summary: summary.textContent,
  summaryAria: summary.getAttribute("aria-label"),
  listBootAria: list.getAttribute("aria-label"),
  toolbarAria: byClass(list, "changes-ledger-toolbar")[0]?.getAttribute("aria-label") || "",
  scrollAria: byClass(list, "changes-ledger-scroll")[0]?.getAttribute("aria-label") || "",
  filters,
  dates: byClass(list, "changes-ledger-date").map(node => node.textContent),
  categories: byClass(list, "changes-ledger-category").map(node => node.textContent),
  headlines: byClass(list, "changes-ledger-headline").map(node => node.textContent),
  metadata: byClass(list, "changes-ledger-meta-text").map(node => node.textContent),
  sourceActions: byClass(list, "changes-ledger-source").map(node => ({
    text: node.textContent,
    aria: node.getAttribute("aria-label"),
    href: node.href
  })),
  wordmarks: byClass(list, "changes-ledger-wordmark").map(node => node.textContent),
  filteredCategories: input.clickCampaign
    ? byClass(list, "changes-ledger-category").map(node => node.textContent)
    : [],
  empty: byClass(list, "changes-ledger-empty").map(node => node.textContent),
  payloadUnchanged: originalPayload === JSON.stringify(input.recentChanges)
};`,
  context
);
process.stdout.write(JSON.stringify(context.result));
"""


def payload():
    return {
        "window": {"days": 14, "end_date": "2026-09-07"},
        "items": [
            {
                "id": "campaign-source-item",
                "category": "campaign",
                "headline": "Titre source — octets préservés",
                "summary": "Concrete candidate, endorsement, selection or campaign-status change.",
                "trusted_change_at": "2026-09-07T08:30:00Z",
                "trusted_change_date_kind": "source_published",
                "published_at": "2026-09-07T08:30:00Z",
                "primary_source": {
                    "name": "Le Média Source",
                    "url": "https://example.test/campaign",
                },
                "source_icon_key": "le-media-source",
                "candidate_names": ["Candidate Source"],
                "supporting_source_count": 1,
            },
            {
                "id": "polling-generated-item",
                "category": "polling",
                "headline": "Institut Source first-round poll, fieldwork 5 Sep 2026–6 Sep 2026, contains 2 published hypotheses.",
                "summary": "Fieldwork ended 6 Sep 2026 · fieldwork 2026-09-05–2026-09-06 · 1,234 respondents.",
                "trusted_change_at": "2026-09-06",
                "trusted_change_date_kind": "fieldwork_ended",
                "published_at": None,
                "primary_source": {
                    "name": "Institut Source",
                    "url": "https://example.test/poll",
                },
                "source_icon_key": "institut-source",
                "candidate_names": [],
                "supporting_source_count": 0,
            },
            {
                "id": "fact-source-item",
                "category": "fact_check",
                "headline": "Déclaration source inchangée",
                "summary": "Vérif Source · rating: Plutôt Vrai · claimant: Personne Source.",
                "trusted_change_at": "2026-09-05",
                "trusted_change_date_kind": "review_published",
                "published_at": "2026-09-05",
                "primary_source": {
                    "name": "Vérif Source",
                    "url": "https://example.test/review",
                },
                "source_icon_key": "verif-source",
                "candidate_names": ["Personne Source"],
                "supporting_source_count": 0,
            },
        ],
    }


def run_harness(locale="fr", state="loaded", recent_changes=None, click_campaign=False):
    href = "https://example.test/" if locale == "fr" else "https://example.test/?lang=en"
    result = subprocess.run(
        ["node", "-e", WHAT_CHANGED_HARNESS],
        cwd=ROOT,
        input=json.dumps(
            {
                "href": href,
                "state": state,
                "recentChanges": recent_changes,
                "clickCampaign": click_campaign,
                "polls": {
                    "events": [
                        {
                            "pollster": "Institut Source",
                            "fieldwork_start": "2026-09-05",
                            "fieldwork_end": "2026-09-06",
                            "publication_date": "2026-09-07",
                            "source_url": "https://example.test/poll",
                        },
                        {
                            "pollster": "Institut Source",
                            "fieldwork_start": "2026-09-05",
                            "fieldwork_end": "2026-09-06",
                            "publication_date": "2026-09-07",
                            "source_url": "https://example.test/poll",
                        },
                    ]
                },
                "claims": {
                    "reviews": [
                        {
                            "review_url": "https://example.test/review",
                            "rating": "Plutôt Vrai",
                            "claimant": "Personne Source",
                        }
                    ]
                },
            },
            ensure_ascii=False,
        ),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


class WhatChangedLocalizationTests(unittest.TestCase):
    def test_french_title_and_compact_summary(self):
        result = run_harness(recent_changes=payload())
        self.assertEqual(result["title"], "ÉVOLUTIONS")
        self.assertEqual(result["summary"], "3 ÉVOLUTIONS · 14 J")

    def test_english_title_and_summary_remain_english(self):
        result = run_harness(locale="en", recent_changes=payload())
        self.assertEqual(result["title"], "WHAT CHANGED")
        self.assertEqual(result["summary"], "3 CHANGES · LAST 14 DAYS")

    def test_filters_localize_but_keep_stable_identity(self):
        result = run_harness(recent_changes=payload())
        self.assertEqual(
            [(item["key"], item["text"]) for item in result["filters"]],
            [
                ("all", "TOUT 3"),
                ("campaign", "CAMPAGNE 1"),
                ("polling", "SONDAGES 1"),
                ("runoff", "2E TOUR 0"),
                ("checks", "VIGILANCE 1"),
            ],
        )

    def test_filtering_behavior_uses_category_ids(self):
        result = run_harness(recent_changes=payload(), click_campaign=True)
        self.assertEqual(result["filteredCategories"], ["CAMPAGNE"])

    def test_french_date_and_day_headings_are_compact(self):
        result = run_harness(recent_changes=payload())
        self.assertEqual(result["dates"], ["AUJ. · 7 SEPT.", "HIER · 6 SEPT.", "5 SEPT."])

    def test_source_headlines_and_publishers_are_unchanged(self):
        result = run_harness(recent_changes=payload())
        self.assertIn("Titre source — octets préservés", result["headlines"])
        self.assertIn("Déclaration source inchangée", result["headlines"])
        self.assertIn("Le Média Source", result["wordmarks"])
        self.assertIn("Vérif Source", result["wordmarks"])

    def test_generated_poll_copy_localizes_from_structured_fields(self):
        result = run_harness(recent_changes=payload())
        self.assertIn(
            "Institut Source · 1er tour · terrain 5 sept. 2026–6 sept. 2026 · 2 hypothèses",
            result["headlines"],
        )

    def test_source_link_action_localizes(self):
        result = run_harness(recent_changes=payload())
        self.assertTrue(result["sourceActions"])
        self.assertTrue(all(item["text"] == "Source ↗" for item in result["sourceActions"]))
        self.assertIn("Le Média Source", result["sourceActions"][0]["aria"])

    def test_authored_metadata_localizes_without_translating_evidence(self):
        result = run_harness(recent_changes=payload())
        combined = " | ".join(result["metadata"])
        self.assertIn("Publié · Candidature, soutien, sélection ou statut de campagne", combined)
        self.assertIn("Verdict : Plutôt Vrai", combined)
        self.assertIn("Auteur : Personne Source", combined)
        self.assertNotIn("Concrete candidate", combined)

    def test_loading_empty_and_error_states_never_show_keys(self):
        loading = run_harness(state="loading", recent_changes=None)
        empty = run_harness(recent_changes={"window": {"days": 14, "end_date": "2026-09-07"}, "items": []})
        error = run_harness(state="error", recent_changes=None)
        self.assertEqual(loading["summaryAria"], "Chargement du nombre d’évolutions")
        self.assertEqual(empty["empty"], ["Aucune évolution récente"])
        self.assertEqual(error["summary"], "Indisponible")
        self.assertEqual(error["empty"], ["Indisponible"])
        self.assertNotIn("what_changed.", json.dumps([loading, empty, error]))

    def test_locale_switch_preserves_counts_filtering_and_payload(self):
        french = run_harness(recent_changes=payload(), click_campaign=True)
        english = run_harness(locale="en", recent_changes=payload(), click_campaign=True)
        self.assertEqual(
            [item["text"].rsplit(" ", 1)[-1] for item in french["filters"]],
            [item["text"].rsplit(" ", 1)[-1] for item in english["filters"]],
        )
        self.assertEqual(len(french["filteredCategories"]), len(english["filteredCategories"]))
        self.assertTrue(french["payloadUnchanged"])
        self.assertTrue(english["payloadUnchanged"])


if __name__ == "__main__":
    unittest.main()
