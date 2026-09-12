from pathlib import Path
import ast
import html
import json
import re
import subprocess
import unittest
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
INDEX_TEXT = (ROOT / "index.html").read_text(encoding="utf-8")
RUNTIME_TEXT = (ROOT / "assets" / "localization.js").read_text(encoding="utf-8")
COVERAGE_MODAL_TEXT = (ROOT / "assets" / "election-coverage-modal.js").read_text(encoding="utf-8")
TOPIC_COVERAGE_TEXT = (ROOT / "assets" / "topic-coverage-modal.js").read_text(encoding="utf-8")
HYBRID_TEXT = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")
CATALOG_TEXT = (ROOT / "locales" / "en.js").read_text(encoding="utf-8")
FR_CATALOG_TEXT = (ROOT / "locales" / "fr.js").read_text(encoding="utf-8")
TITLE_KEY = "page.france_2027_signal_lab_source_linked_election_signals"
TITLE_TEXT = "France 2027 Signal Lab — Source-Linked Election Signals"
FRENCH_TITLE_TEXT = "France 2027 Signal Lab — Signaux électoraux sourcés"
DYNAMIC_KEYS = {
    "candidate.scrutiny.archive_by",
    "dashboard.candidate_portrait_alt",
    "dashboard.claims.review_count_label",
    "dashboard.news.campaign_agenda_unavailable",
    "dashboard.news.candidate_coverage_unavailable",
    "dashboard.news.relevant_news_unavailable",
    "dashboard.poll.partial_reported_field",
    "dashboard.runoff.smallest_reported_margin",
    "dashboard.source.open_category_source_from_publisher",
    "signal_board.claims.latest_review",
    "signal_board.media.latest_accepted_item",
}


def catalog_messages(source=CATALOG_TEXT, catalog_name="English"):
    match = re.search(
        r"const messages = Object\.freeze\((\{.*?\})\);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"{catalog_name} catalog object was not found")
    return json.loads(match.group(1))


def canonical_agenda_topics():
    source = (ROOT / "fetch_news_wire.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        "CAMPAIGN_AGENDA_TOPICS",
        "POLICY_AGENDA_TOPICS",
    }
    definitions = {}

    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in names:
            continue
        definitions[target.id] = ast.literal_eval(node.value)

    if set(definitions) != names:
        raise AssertionError("Canonical Agenda taxonomy definitions were not found")

    return {
        "campaign": [
            (topic["id"], topic["label"])
            for topic in definitions["CAMPAIGN_AGENDA_TOPICS"]
        ],
        "policy": [
            (topic["id"], topic["label"])
            for topic in definitions["POLICY_AGENDA_TOPICS"]
        ],
    }


RUNTIME_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));

class Element {
  constructor(attributes = {}, textContent = "") {
    this.attributes = new Map(Object.entries(attributes));
    this.textContent = textContent;
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
}

const textElement = new Element(
  { "data-i18n": "static.text" },
  "Contenu source français"
);
const ariaElement = new Element(
  { "data-i18n-aria-label": "static.aria", "aria-label": "Libellé source français" }
);
const pollMeta = new Element(
  {
    id: "context-poll-meta",
    "data-i18n-fr27-tooltip": "static.tooltip",
    "data-fr27-tooltip": "Infobulle source française"
  },
  "Loading…"
);
const sourceEvidence = [
  new Element({}, "Titre de source"),
  new Element({}, "Le Monde"),
  new Element({}, "parrainage"),
  new Element({}, "Ipsos · Ifop")
];
const frenchLink = new Element({ "data-fr27-language": "fr", href: "./" });
const englishLink = new Element({ "data-fr27-language": "en", href: "?lang=en" });
const documentListeners = new Map();
const windowListeners = new Map();
const timers = [];
const warnings = [];
const location = new URL(input.href);

const addListener = (listeners, type, callback) => {
  const callbacks = listeners.get(type) || [];
  callbacks.push(callback);
  listeners.set(type, callbacks);
};
const dispatch = (listeners, type) => {
  for (const callback of [...(listeners.get(type) || [])]) callback();
};
const flushTimers = () => {
  while (timers.length) timers.shift()();
};

const documentElement = {
  dataset: { siteRoot: "./" },
  lang: "fr"
};
const documentObject = {
  documentElement,
  baseURI: location.href,
  readyState: "loading",
  title: "",
  querySelectorAll(selector) {
    return {
      "[data-i18n]": [textElement],
      "[data-i18n-aria-label]": [ariaElement],
      "[data-i18n-fr27-tooltip]": [pollMeta],
      "[data-fr27-language]": [frenchLink, englishLink]
    }[selector] || [];
  },
  addEventListener(type, callback) {
    addListener(documentListeners, type, callback);
  }
};
const windowObject = {
  document: documentObject,
  location,
  FR27_LOCALES: {
    en: {
      "static.text": "English catalog text",
      "static.aria": "English catalog label",
      "static.tooltip": "English catalog tooltip",
      "english.only": "English fallback for {name}"
    },
    fr: {
      "static.text": "Texte français actif",
      "static.aria": "Libellé français actif",
      "static.tooltip": "Infobulle française active"
    }
  },
  console: {
    warn(...values) {
      warnings.push(values.map(String));
    }
  },
  history: {
    replaceState(_state, _title, value) {
      location.href = new URL(value, location.href).href;
    }
  },
  addEventListener(type, callback) {
    addListener(windowListeners, type, callback);
  },
  setTimeout(callback) {
    timers.push(callback);
    return timers.length;
  }
};

const context = {
  window: windowObject,
  globalThis: windowObject,
  URL,
  URLSearchParams,
  Intl,
  Object,
  String,
  Number,
  Boolean
};
vm.runInNewContext(
  fs.readFileSync("assets/localization.js", "utf8"),
  context
);
dispatch(documentListeners, "DOMContentLoaded");

// Register normalization after localization to prove that the deferred link
// refresh observes the settled URL regardless of listener order.
windowObject.addEventListener("hashchange", () => {
  const accepted = new Set([
    "#signal-candidates",
    "#signal-agenda",
    "#signal-events",
    "#signal-issues",
    "#signal-runoff"
  ]);
  if (!accepted.has(location.hash)) {
    windowObject.history.replaceState(null, "", "#signal-candidates");
  }
});

const linkSnapshot = () => ({
  fr: frenchLink.getAttribute("href"),
  en: englishLink.getAttribute("href")
});
const changeHash = value => {
  location.hash = value;
  dispatch(windowListeners, "hashchange");
  flushTimers();
  return linkSnapshot();
};

const bootLinks = linkSnapshot();
const currentLinks = changeHash("#signal-events");
const normalizedLinks = changeHash("#rejected-workspace");

pollMeta.textContent = "Ipsos · Ifop";
windowObject.FR27I18N.applyStaticTranslations();

const api = windowObject.FR27I18N;
const result = {
  locale: api.locale,
  staticText: textElement.textContent,
  staticAria: ariaElement.getAttribute("aria-label"),
  staticTooltip: pollMeta.getAttribute("data-fr27-tooltip"),
  pollMetaText: pollMeta.textContent,
  sourceEvidence: sourceEvidence.map(element => element.textContent),
  bootLinks,
  currentLinks,
  normalizedLinks,
  normalizedHash: location.hash,
  englishCatalogFallback: api.t(
    "english.only",
    { name: "Camille" },
    "Caller fallback"
  ),
  legacyParameterizedCall: api.t(
    "english.only",
    { name: "Alex" }
  ),
  callerInterpolation: api.t(
    "missing.interpolation",
    { name: "Camille" },
    "Fallback for {name}"
  ),
  callerPluralOne: api.t(
    "missing.plural.one",
    { count: 1 },
    "{count, plural, one {record} other {records}}: {count}"
  ),
  callerPluralOther: api.t(
    "missing.plural.other",
    { count: 2 },
    "{count, plural, one {record} other {records}}: {count}"
  ),
  finalDiagnostic: api.t("missing.no_fallback"),
  warnings
};
process.stdout.write(JSON.stringify(result));
"""


def run_runtime_harness(href):
    completed = subprocess.run(
        ["node", "-e", RUNTIME_HARNESS],
        cwd=ROOT,
        input=json.dumps({"href": href}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


FOOTER_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const indexSource = fs.readFileSync("index.html", "utf8");

class Element {
  constructor(attributes = {}, textContent = "") {
    this.attributes = new Map(Object.entries(attributes));
    this.textContent = textContent;
    this.parentElement = null;
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
}

const footerStart = indexSource.indexOf("<!-- DATASET SCALE -->");
const footerEnd = indexSource.indexOf("<!-- UTILITY -->", footerStart);
const footerMarkup = indexSource.slice(footerStart, footerEnd);
const footerLabels = [
  ...footerMarkup.matchAll(
    /<span\b[^>]*data-i18n="([^"]+)"[^>]*>([^<]*)<\/span>/g
  )
].map(match => new Element(
  { "data-i18n": match[1] },
  match[2].trim()
));

const footerValueIds = [
  "fr27-hud-news-value",
  "fr27-hud-publishers-value",
  "fr27-hud-recent-value",
  "fr27-hud-candidate-watch-value"
];
const footerValues = new Map(
  footerValueIds.map(id => [
    id,
    {
      textContent: "—",
      classList: { remove() {} },
      removeAttribute() {}
    }
  ])
);

const headerMetrics = input.metrics.map(metric => {
  const strong = new Element({}, String(metric.value));
  const label = new Element({}, metric.label);
  const container = new Element(
    { "data-media-pulse-metric": metric.key },
    `${metric.value} ${metric.label}`
  );
  container.querySelector = selector =>
    selector === "strong" ? strong : null;
  strong.parentElement = container;
  label.parentElement = container;
  return { container, strong, label };
});

const listeners = new Map();
const addListener = (type, callback) => {
  const callbacks = listeners.get(type) || [];
  callbacks.push(callback);
  listeners.set(type, callbacks);
};
const location = new URL(input.href);
const documentElement = {
  dataset: { siteRoot: "./" },
  lang: "fr"
};
const documentObject = {
  documentElement,
  baseURI: location.href,
  readyState: "loading",
  title: "",
  querySelectorAll(selector) {
    if (selector === "[data-i18n]") return footerLabels;
    if (
      selector ===
      "#top-media-pulse-metrics [data-media-pulse-metric]"
    ) {
      return headerMetrics.map(metric => metric.container);
    }
    if (selector === "#top-media-pulse-metrics *") {
      return headerMetrics.flatMap(metric => [
        metric.container,
        metric.strong,
        metric.label
      ]);
    }
    return [];
  },
  addEventListener(type, callback) {
    addListener(type, callback);
  }
};
const windowObject = {
  document: documentObject,
  location,
  console: { warn() {} },
  addEventListener() {},
  setTimeout(callback) {
    callback();
    return 1;
  }
};
const context = {
  window: windowObject,
  globalThis: windowObject,
  document: documentObject,
  location,
  URL,
  URLSearchParams,
  Intl,
  Object,
  String,
  Number,
  Boolean,
  Array,
  hud: {
    contains() {
      return false;
    },
    querySelector(selector) {
      return footerValues.get(selector.replace(/^#/, "")) || null;
    }
  },
  fr27HudExtractMetric() {
    return null;
  }
};

vm.runInNewContext(
  fs.readFileSync("locales/en.js", "utf8"),
  context
);
vm.runInNewContext(
  fs.readFileSync("locales/fr.js", "utf8"),
  context
);
vm.runInNewContext(
  fs.readFileSync("assets/localization.js", "utf8"),
  context
);

const extractStart = indexSource.indexOf(
  "  function fr27HudExtractExactMetric"
);
const extractEnd = indexSource.indexOf(
  "  fr27HudRefreshMetrics();",
  extractStart
);
vm.runInNewContext(
  indexSource.slice(extractStart, extractEnd) +
    "\nfr27HudRefreshMetrics();",
  context
);

for (const callback of listeners.get("DOMContentLoaded") || []) {
  callback();
}

process.stdout.write(JSON.stringify({
  footerLabels: Object.fromEntries(
    footerLabels.map(label => [
      label.getAttribute("data-i18n"),
      label.textContent
    ])
  ),
  footerValues: Object.fromEntries(
    [...footerValues.entries()].map(([id, element]) => [
      id,
      element.textContent
    ])
  )
}));
"""


def run_footer_harness(href, metrics):
    completed = subprocess.run(
        ["node", "-e", FOOTER_HARNESS],
        cwd=ROOT,
        input=json.dumps({"href": href, "metrics": metrics}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


TAXONOMY_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const source = fs.readFileSync(input.path, "utf8").replace(/\r\n/g, "\n");
const start = source.indexOf(input.startMarker);
const end = source.indexOf(input.endMarker, start);

if (start === -1 || end === -1) {
  throw new Error(`Agenda taxonomy helper was not found in ${input.path}`);
}

const windowObject = {
  location: new URL(input.href),
  console: { warn() {} }
};
const context = {
  window: windowObject,
  globalThis: windowObject,
  URL,
  URLSearchParams,
  Intl,
  Object,
  String,
  Number,
  Boolean,
  Array,
  input,
  result: null
};

vm.runInNewContext(fs.readFileSync("locales/en.js", "utf8"), context);
vm.runInNewContext(fs.readFileSync("locales/fr.js", "utf8"), context);
vm.runInNewContext(
  fs.readFileSync("assets/localization.js", "utf8"),
  context
);
vm.runInNewContext(
  source.slice(start, end) +
    "\nresult = input.topics.map(topic => ({" +
    " label: agendaTopicLabel(topic)," +
    " compact: typeof compactAgendaTopicLabel === 'function'" +
    "   ? compactAgendaTopicLabel(topic) : null," +
    " topic" +
    "}));",
  context
);

process.stdout.write(JSON.stringify(context.result));
"""


def run_taxonomy_harness(path, start_marker, end_marker, href, topics):
    completed = subprocess.run(
        ["node", "-e", TAXONOMY_HARNESS],
        cwd=ROOT,
        input=json.dumps(
            {
                "path": str(path.relative_to(ROOT)),
                "startMarker": start_marker,
                "endMarker": end_marker,
                "href": href,
                "topics": topics,
            }
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


COMPACT_SURFACE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const source = fs.readFileSync(input.path, "utf8").replace(/\r\n/g, "\n");
const windowObject = {
  location: new URL(input.href),
  console: { warn() {} }
};
const context = {
  window: windowObject,
  globalThis: windowObject,
  URL,
  URLSearchParams,
  Intl,
  Object,
  String,
  Number,
  Boolean,
  Array,
  Math,
  input,
  result: null
};

vm.runInNewContext(fs.readFileSync("locales/en.js", "utf8"), context);
vm.runInNewContext(fs.readFileSync("locales/fr.js", "utf8"), context);
vm.runInNewContext(
  fs.readFileSync("assets/localization.js", "utf8"),
  context
);

if (input.surface === "media_pulse") {
  const helperStart = source.indexOf("  const translate =");
  const helperEnd = source.indexOf(
    "  const renderStrongDateOrUnavailable",
    helperStart
  );
  const rowsStart = source.indexOf("    const maxTopicDays =");
  const rowsEnd = source.indexOf("    const publisherRows =", rowsStart);
  context.model = { topicCoverage: input.topics };
  context.escapeHtml = value => String(value);
  context.escapeAttribute = value => String(value);
  vm.runInNewContext(
    source.slice(helperStart, helperEnd) +
      source.slice(rowsStart, rowsEnd) +
      "\nresult = { markup: topicRows, topics: model.topicCoverage };",
    context
  );
} else if (input.surface === "coverage_analysis") {
  const helperStart = source.indexOf("  const localizer =");
  const helperEnd = source.indexOf(
    "  const normalizePublisher =",
    helperStart
  );
  const rowsStart = source.indexOf("  const renderTopicRows =");
  const rowsEnd = source.indexOf("  const renderPublisherRows =", rowsStart);
  context.topics = [];
  context.highlightedTopic = input.topics[0]?.id || "";
  vm.runInNewContext(
    source.slice(helperStart, helperEnd) +
      source.slice(rowsStart, rowsEnd) +
      "\ntopics.push(...input.topics.map(normalizeTopic));" +
      "\nresult = { markup: renderTopicRows(), inputTopics: input.topics };",
    context
  );
} else {
  throw new Error(`Unknown compact surface: ${input.surface}`);
}

process.stdout.write(JSON.stringify(context.result));
"""


def run_compact_surface_harness(surface, href, topics):
    path = (
        ROOT / "assets" / "hybrid-dashboard.js"
        if surface == "media_pulse"
        else ROOT / "assets" / "topic-coverage-modal.js"
    )
    completed = subprocess.run(
        ["node", "-e", COMPACT_SURFACE_HARNESS],
        cwd=ROOT,
        input=json.dumps(
            {
                "surface": surface,
                "path": str(path.relative_to(ROOT)),
                "href": href,
                "topics": topics,
            }
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


ADAPTER_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const source = fs.readFileSync(input.path, "utf8").replace(/\r\n/g, "\n");
const start = source.indexOf("  const translate =");
const end = source.indexOf(input.endMarker, start);
const adapter = source.slice(start, end);
const calls = [];
const context = {
  result: null,
  localizer: null,
  globalThis: {
    FR27I18N: {
      t(key, parameters, fallback) {
        calls.push({ key, parameters, fallback });
        return fallback;
      }
    }
  }
};
context.localizer = context.globalThis.FR27I18N;
vm.runInNewContext(
  `${adapter}\nresult = translate(` +
    `"missing.adapter.key", "Adapter fallback {count}", { count: 2 });`,
  context
);
process.stdout.write(JSON.stringify({ result: context.result, calls }));
"""


def run_adapter_harness(path, end_marker):
    completed = subprocess.run(
        ["node", "-e", ADAPTER_HARNESS],
        cwd=ROOT,
        input=json.dumps(
            {"path": str(path.relative_to(ROOT)), "endMarker": end_marker}
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


class LocalizationFoundationTests(unittest.TestCase):
    def test_english_catalog_has_unique_keys(self):
        messages = catalog_messages()
        self.assertGreater(len(messages), 0)
        self.assertEqual(len(messages), len(set(messages)))
        self.assertIn(TITLE_KEY, messages)

    def test_complete_dynamic_message_keys_are_catalogued(self):
        messages = catalog_messages()
        self.assertEqual(len(DYNAMIC_KEYS), 11)
        self.assertTrue(DYNAMIC_KEYS.issubset(messages))
        self.assertEqual(
            messages["candidate.scrutiny.archive_by"],
            "Archive · BY",
        )

    def test_complete_agenda_taxonomy_catalog_uses_canonical_ids(self):
        expected_campaign = [
            ("legal_eligibility", "Legal cases & eligibility"),
            ("selection_strategy", "Primaries & party strategy"),
            ("candidacies_endorsements", "Candidacies & endorsements"),
            (
                "rules_calendar",
                "Rules, calendar & campaign mechanics",
            ),
            (
                "positioning_integrity",
                "Positioning & political image",
            ),
            ("polls_race", "Polling & race narratives"),
        ]
        expected_policy = [
            ("economy_public_finances", "Economy & Public Finances"),
            (
                "work_purchasing_power_pensions",
                "Work, Purchasing Power & Pensions",
            ),
            (
                "immigration_identity_secularism",
                "Immigration, Identity & Secularism",
            ),
            ("security_justice", "Security & Justice"),
            (
                "health_education_public_services",
                "Health, Education & Public Services",
            ),
            (
                "climate_energy_agriculture",
                "Climate, Energy & Agriculture",
            ),
            (
                "europe_defence_foreign_affairs",
                "Europe, Defence & Foreign Affairs",
            ),
            (
                "institutions_democracy_territories",
                "Institutions, Democracy & Territories",
            ),
        ]
        expected_french = {
            "legal_eligibility": "Affaires judiciaires et éligibilité",
            "selection_strategy": "Primaires et stratégies partisanes",
            "candidacies_endorsements": "Candidatures et soutiens",
            "rules_calendar": (
                "Règles, calendrier et organisation de la campagne"
            ),
            "positioning_integrity": "Positionnement et image politique",
            "polls_race": "Sondages et rapports de force",
            "economy_public_finances": "Économie et finances publiques",
            "work_purchasing_power_pensions": (
                "Travail, pouvoir d’achat et retraites"
            ),
            "immigration_identity_secularism": (
                "Immigration, identité et laïcité"
            ),
            "security_justice": "Sécurité et justice",
            "health_education_public_services": (
                "Santé, éducation et services publics"
            ),
            "climate_energy_agriculture": "Climat, énergie et agriculture",
            "europe_defence_foreign_affairs": (
                "Europe, défense et affaires étrangères"
            ),
            "institutions_democracy_territories": (
                "Institutions, démocratie et territoires"
            ),
        }

        canonical = canonical_agenda_topics()
        self.assertEqual(canonical["campaign"], expected_campaign)
        self.assertEqual(canonical["policy"], expected_policy)

        english = catalog_messages()
        french = catalog_messages(FR_CATALOG_TEXT, "French")
        expected_keys = {
            f"agenda_topic.{topic_id}"
            for topic_id, _label in expected_campaign + expected_policy
        }
        self.assertEqual(
            {key for key in english if key.startswith("agenda_topic.")},
            expected_keys,
        )
        self.assertEqual(
            {key for key in french if key.startswith("agenda_topic.")},
            expected_keys,
        )

        for topic_id, canonical_label in expected_campaign + expected_policy:
            key = f"agenda_topic.{topic_id}"
            self.assertEqual(english[key], canonical_label)
            self.assertEqual(french[key], expected_french[topic_id])

    def test_agenda_taxonomy_labels_resolve_by_id_across_surfaces(self):
        canonical = canonical_agenda_topics()
        canonical_topics = canonical["campaign"] + canonical["policy"]
        topics = [
            {
                "id": topic_id,
                "label": (
                    "Harmless alternate poll label"
                    if topic_id == "polls_race"
                    else canonical_label
                ),
                "headline": "Titre source inchangé",
                "publisher": "Le Monde",
                "matched_terms": ["parrainage"],
            }
            for topic_id, canonical_label in canonical_topics
        ]
        topics.append(
            {
                "id": "unknown_test_topic",
                "label": "Canonical fallback label",
                "headline": "Autre titre source inchangé",
                "publisher": "France Info",
                "matched_terms": ["élection"],
            }
        )

        expected_french = [
            "Affaires judiciaires et éligibilité",
            "Primaires et stratégies partisanes",
            "Candidatures et soutiens",
            "Règles, calendrier et organisation de la campagne",
            "Positionnement et image politique",
            "Sondages et rapports de force",
            "Économie et finances publiques",
            "Travail, pouvoir d’achat et retraites",
            "Immigration, identité et laïcité",
            "Sécurité et justice",
            "Santé, éducation et services publics",
            "Climat, énergie et agriculture",
            "Europe, défense et affaires étrangères",
            "Institutions, démocratie et territoires",
            "Canonical fallback label",
        ]
        expected_english = [
            canonical_label for _topic_id, canonical_label in canonical_topics
        ] + ["Canonical fallback label"]
        surfaces = (
            (
                ROOT / "index.html",
                "    const translate =",
                "    const palette =",
            ),
            (
                ROOT / "assets" / "hybrid-dashboard.js",
                "  const translate =",
                "  const renderStrongDateOrUnavailable",
            ),
            (
                ROOT / "assets" / "topic-coverage-modal.js",
                "  const localizer =",
                "  const collator =",
            ),
        )
        locale_cases = (
            ("https://example.test/", expected_french),
            ("https://example.test/?lang=en", expected_english),
        )

        for href, expected_labels in locale_cases:
            rendered_by_surface = []
            for path, start_marker, end_marker in surfaces:
                with self.subTest(locale=href, surface=path.name):
                    rendered = run_taxonomy_harness(
                        path,
                        start_marker,
                        end_marker,
                        href,
                        topics,
                    )
                    labels = [item["label"] for item in rendered]
                    self.assertEqual(labels, expected_labels)
                    self.assertEqual(
                        [item["topic"] for item in rendered],
                        topics,
                    )
                    rendered_by_surface.append(labels)
            self.assertTrue(
                all(
                    labels == rendered_by_surface[0]
                    for labels in rendered_by_surface[1:]
                )
            )

        self.assertNotIn("compactLabels[topic.label]", HYBRID_TEXT)
        self.assertNotIn("escapeHtml(topic.label)", INDEX_TEXT)

    def test_compact_agenda_taxonomy_catalog_and_resolution(self):
        canonical = canonical_agenda_topics()
        canonical_topics = canonical["campaign"] + canonical["policy"]
        expected_french = {
            "candidacies_endorsements": "Candidatures",
            "selection_strategy": "Primaires",
            "polls_race": "Sondages",
            "legal_eligibility": "Justice & éligibilité",
            "rules_calendar": "Règles & calendrier",
            "positioning_integrity": "Positionnement",
            "economy_public_finances": "Économie & finances",
            "work_purchasing_power_pensions": "Travail & pouvoir d’achat",
            "immigration_identity_secularism": "Immigration & identité",
            "security_justice": "Sécurité & justice",
            "health_education_public_services": "Santé & éducation",
            "climate_energy_agriculture": "Climat & énergie",
            "europe_defence_foreign_affairs": "Europe & défense",
            "institutions_democracy_territories": (
                "Institutions & démocratie"
            ),
        }
        expected_english = {
            "legal_eligibility": "Legal & eligibility",
            "selection_strategy": "Primaries & strategy",
            "candidacies_endorsements": "Candidacies & endors.",
            "rules_calendar": "Rules & mechanics",
            "positioning_integrity": "Positioning & political image",
            "polls_race": "Polling & race",
            "economy_public_finances": "Economy & finances",
            "work_purchasing_power_pensions": "Work & pensions",
            "immigration_identity_secularism": "Immigration & identity",
            "security_justice": "Security & justice",
            "health_education_public_services": "Health & education",
            "climate_energy_agriculture": "Climate & energy",
            "europe_defence_foreign_affairs": "Europe & defence",
            "institutions_democracy_territories": (
                "Institutions & territories"
            ),
        }
        expected_keys = {
            f"agenda_topic_short.{topic_id}"
            for topic_id, _label in canonical_topics
        }
        english = catalog_messages()
        french = catalog_messages(FR_CATALOG_TEXT, "French")

        self.assertEqual(
            {
                key
                for key in english
                if key.startswith("agenda_topic_short.")
            },
            expected_keys,
        )
        self.assertEqual(
            {
                key
                for key in french
                if key.startswith("agenda_topic_short.")
            },
            expected_keys,
        )
        for topic_id, _canonical_label in canonical_topics:
            key = f"agenda_topic_short.{topic_id}"
            self.assertEqual(french[key], expected_french[topic_id])
            self.assertEqual(english[key], expected_english[topic_id])

        topics = [
            {
                "id": "polls_race",
                "label": "Harmless alternate poll label",
            },
            {
                "id": "unknown_test_topic",
                "label": "Canonical fallback label",
            },
        ]
        french_result = run_taxonomy_harness(
            ROOT / "assets" / "hybrid-dashboard.js",
            "  const translate =",
            "  const renderStrongDateOrUnavailable",
            "https://example.test/",
            topics,
        )
        english_result = run_taxonomy_harness(
            ROOT / "assets" / "hybrid-dashboard.js",
            "  const translate =",
            "  const renderStrongDateOrUnavailable",
            "https://example.test/?lang=en",
            topics,
        )
        detailed_result = run_taxonomy_harness(
            ROOT / "index.html",
            "    const translate =",
            "    const palette =",
            "https://example.test/",
            topics,
        )

        self.assertEqual(
            [(item["label"], item["compact"]) for item in french_result],
            [
                ("Sondages et rapports de force", "Sondages"),
                ("Canonical fallback label", "Canonical fallback label"),
            ],
        )
        self.assertEqual(
            [(item["label"], item["compact"]) for item in english_result],
            [
                ("Polling & race narratives", "Polling & race"),
                ("Canonical fallback label", "Canonical fallback label"),
            ],
        )
        self.assertEqual(
            [(item["label"], item["compact"]) for item in detailed_result],
            [
                ("Sondages et rapports de force", None),
                ("Canonical fallback label", None),
            ],
        )

    def test_constrained_taxonomy_rows_preserve_full_semantics_and_data(self):
        evidence = {
            "headline": "Titre source inchangé",
            "publisher": "Le Monde",
            "matched_terms": ["parrainage"],
        }
        media_topic = {
            "id": "polls_race",
            "label": "Harmless alternate poll label",
            "sourceDays": 17,
            "itemCount": 23,
            "publishers": 5,
            **evidence,
        }
        coverage_topic = {
            "id": "polls_race",
            "label": "Harmless alternate poll label",
            "source_day_count": 17,
            "item_count": 23,
            "publisher_count": 5,
            "active_day_count": 9,
            **evidence,
        }

        french_media = run_compact_surface_harness(
            "media_pulse",
            "https://example.test/",
            [media_topic],
        )
        english_media = run_compact_surface_harness(
            "media_pulse",
            "https://example.test/?lang=en",
            [media_topic],
        )
        french_coverage = run_compact_surface_harness(
            "coverage_analysis",
            "https://example.test/",
            [coverage_topic],
        )
        english_coverage = run_compact_surface_harness(
            "coverage_analysis",
            "https://example.test/?lang=en",
            [coverage_topic],
        )

        for result, original in (
            (french_media, media_topic),
            (english_media, media_topic),
        ):
            self.assertEqual(result["topics"], [original])
            self.assertIn('data-hybrid-media-topic="polls_race"', result["markup"])
            self.assertIn("<strong>17</strong>", result["markup"])
            self.assertNotIn("Harmless alternate poll label", result["markup"])

        self.assertRegex(
            french_media["markup"],
            r"<span>\s*Sondages\s*</span>",
        )
        self.assertIn("Sondages et rapports de force", french_media["markup"])
        self.assertRegex(
            english_media["markup"],
            r"<span>\s*Polling & race\s*</span>",
        )
        self.assertIn("Polling & race narratives", english_media["markup"])

        for result in (french_coverage, english_coverage):
            self.assertEqual(result["inputTopics"], [coverage_topic])
            self.assertIn('data-tcm-topic-row="polls_race"', result["markup"])
            self.assertRegex(result["markup"], r"<b>17</b>")
            self.assertNotIn("Harmless alternate poll label", result["markup"])

        self.assertRegex(
            french_coverage["markup"],
            r'aria-label="Sondages et rapports de force"\s*>Sondages</strong>',
        )
        self.assertRegex(
            english_coverage["markup"],
            (
                r'aria-label="Polling &amp; race narratives"\s*>'
                r'Polling &amp; race</strong>'
            ),
        )
        self.assertIn("a.canonicalLabel", TOPIC_COVERAGE_TEXT)

    def test_runtime_exposes_approved_foundation_api(self):
        for declaration in (
            "const t =",
            "const formatDate =",
            "const formatNumber =",
            "const formatPercent =",
            "const pluralCategory =",
            "const siteUrl =",
            "const buildLocaleUrl =",
            "const applyDocumentTitle =",
        ):
            self.assertIn(declaration, RUNTIME_TEXT)
        self.assertIn("global.FR27I18N = api;", RUNTIME_TEXT)

    def test_index_bootstraps_catalog_before_runtime(self):
        opening = re.search(r"<html\b[^>]*>", INDEX_TEXT, re.I)
        self.assertIsNotNone(opening)
        opening_tag = opening.group(0)
        self.assertIn("lang=\"fr\"", opening_tag)
        self.assertNotIn("data-locale=", opening_tag)
        self.assertIn("data-site-root=\"./\"", opening_tag)
        self.assertIn(
            "data-i18n-document-title=\"" + TITLE_KEY + "\"",
            opening_tag,
        )
        en_catalog_position = INDEX_TEXT.index(
            "src=\"locales/en.js\""
        )
        fr_catalog_position = INDEX_TEXT.index(
            "src=\"locales/fr.js\""
        )
        runtime_position = INDEX_TEXT.index(
            "src=\"assets/localization.js\""
        )
        self.assertLess(en_catalog_position, runtime_position)
        self.assertLess(fr_catalog_position, runtime_position)

    def test_language_links_follow_current_normalized_workspace_hash(self):
        result = run_runtime_harness(
            "https://example.test/dashboard/?campaign=2027"
            "#signal-candidates"
        )

        expected_hashes = {
            "bootLinks": "signal-candidates",
            "currentLinks": "signal-events",
            "normalizedLinks": "signal-candidates",
        }

        for snapshot_name, expected_hash in expected_hashes.items():
            snapshot = result[snapshot_name]
            french = urlparse(snapshot["fr"])
            english = urlparse(snapshot["en"])

            self.assertEqual(french.fragment, expected_hash)
            self.assertEqual(english.fragment, expected_hash)
            self.assertEqual(
                parse_qs(french.query),
                {"campaign": ["2027"]},
            )
            self.assertEqual(
                parse_qs(english.query),
                {"campaign": ["2027"]},
            )

        self.assertEqual(result["normalizedHash"], "#signal-candidates")

    def test_title_catalogs_preserve_bilingual_contract(self):
        title_match = re.search(
            r"<title>(.*?)</title>",
            INDEX_TEXT,
            re.I | re.DOTALL,
        )
        self.assertIsNotNone(title_match)
        static_title = html.unescape(title_match.group(1).strip())
        messages = catalog_messages()
        self.assertEqual(static_title, FRENCH_TITLE_TEXT)
        self.assertEqual(messages[TITLE_KEY], TITLE_TEXT)
        self.assertIn(FRENCH_TITLE_TEXT, FR_CATALOG_TEXT)


    def test_election_coverage_modal_is_locale_aware(self):
        self.assertIn(
            "const localeTag =",
            COVERAGE_MODAL_TEXT,
        )
        self.assertNotIn(
            '"en-GB"',
            COVERAGE_MODAL_TEXT,
        )
        self.assertIn(
            'translate("coverage_modal.search_coverage"',
            COVERAGE_MODAL_TEXT,
        )
        self.assertIn(
            'translate(',
            COVERAGE_MODAL_TEXT,
        )
        self.assertIn(
            '${escapeHtml(record.publisher)}',
            COVERAGE_MODAL_TEXT,
        )
        self.assertIn(
            '${escapeHtml(record.headline)}',
            COVERAGE_MODAL_TEXT,
        )
        self.assertIn(
            'lang="fr"',
            COVERAGE_MODAL_TEXT,
        )

    def test_election_coverage_modal_keys_exist_in_both_catalogs(self):
        required = {
            "coverage_modal.associated_candidates",
            "coverage_modal.close_election_coverage",
            "coverage_modal.coverage_summary",
            "coverage_modal.election_coverage",
            "coverage_modal.no_matching_coverage",
            "coverage_modal.recent_accepted_election_coverage",
            "coverage_modal.search_coverage",
            "coverage_modal.unavailable",
            "coverage_modal.unknown_publisher",
            "coverage_modal.untitled_coverage_record",
            "coverage_modal.date_unavailable",
            "coverage_modal.source_unavailable",
            "coverage_modal.open_source",
            "coverage_modal.all_results",
            "coverage_modal.showing_results",
            "coverage_modal.adjust_search_or_filters",
            "coverage_modal.filter_by_publisher",
            "coverage_modal.all_publishers",
            "coverage_modal.filter_by_candidate",
            "coverage_modal.all_candidates",
            "coverage_modal.sort_coverage",
            "coverage_modal.newest_first",
            "coverage_modal.oldest_first",
            "coverage_modal.recent_election_coverage",
            "coverage_modal.record",
            "coverage_modal.records",
            "coverage_modal.publisher",
            "coverage_modal.publishers",
            "coverage_modal.latest_24h",
            "coverage_modal.coverage_window",
            "coverage_modal.source_linked_automated_collection",
            "coverage_modal.no_editorial_verification",
            "coverage_modal.not_representative_of_all_french_media",
            "coverage_modal.title",
            "coverage_modal.subtitle",
            "coverage_modal.updated",
        }

        for key in required:
            marker = '"' + key + '":'
            self.assertIn(marker, CATALOG_TEXT)
            self.assertIn(marker, FR_CATALOG_TEXT)

    def test_coverage_analysis_modal_is_locale_aware(self):
        self.assertNotIn(
            '"en-GB"',
            TOPIC_COVERAGE_TEXT,
        )
        self.assertNotIn(
            'localeCompare(b.label, "en")',
            TOPIC_COVERAGE_TEXT,
        )
        self.assertIn(
            'translate(',
            TOPIC_COVERAGE_TEXT,
        )
        self.assertIn(
            '"coverage_analysis.title"',
            TOPIC_COVERAGE_TEXT,
        )
        self.assertIn(
            'new Intl.NumberFormat(',
            TOPIC_COVERAGE_TEXT,
        )
        self.assertIn(
            '${escapeHtml(item.compactLabel)}',
            TOPIC_COVERAGE_TEXT,
        )
        self.assertIn(
            'aria-label="${escapeAttribute(item.label)}"',
            TOPIC_COVERAGE_TEXT,
        )
        self.assertIn(
            '${escapeHtml(item.name)}',
            TOPIC_COVERAGE_TEXT,
        )

    def test_coverage_analysis_keys_exist_in_both_catalogs(self):
        required = {
            "coverage_analysis.accepted_news",
            "coverage_analysis.accepted_reports_per_day",
            "coverage_analysis.active_field_candidate_comparison_unavailable",
            "coverage_analysis.active_field_coverage_shift",
            "coverage_analysis.close_coverage_analysis",
            "coverage_analysis.comparable_active_field_percentage_point_change",
            "coverage_analysis.comparison_unavailable",
            "coverage_analysis.complete_active_field_candidate_coverage_shift",
            "coverage_analysis.complete_publisher_ranking",
            "coverage_analysis.complete_recurring_topic_ranking",
            "coverage_analysis.coverage_window",
            "coverage_analysis.current",
            "coverage_analysis.current_record_range",
            "coverage_analysis.daily_accepted_election_coverage",
            "coverage_analysis.daily_volume",
            "coverage_analysis.insufficient_data",
            "coverage_analysis.main_field",
            "coverage_analysis.publisher_panel_changed",
            "coverage_analysis.recent_activity",
            "coverage_analysis.secondary_field",
            "coverage_analysis.source_days_30_day_context",
            "coverage_analysis.top_publishers",
            "coverage_analysis.topic_coverage",
            "coverage_analysis.unavailable",
            "coverage_analysis.unknown_candidate",
            "coverage_analysis.title",
            "coverage_analysis.updated",
            "coverage_analysis.coverage_summary",
            "coverage_analysis.publishers",
            "coverage_analysis.value_unavailable",
            "coverage_analysis.day",
            "coverage_analysis.days",
            "coverage_analysis.delta_pp",
            "coverage_analysis.raw_delta_pp",
            "coverage_analysis.percentage_point_unit",
            "coverage_analysis.comparison_raw_explanation",
            "coverage_analysis.period_legend",
            "coverage_analysis.candidate_row_comparable",
            "coverage_analysis.candidate_row_raw",
            "coverage_analysis.candidate_row_no_delta",
            "coverage_analysis.active_candidate",
            "coverage_analysis.active_candidates",
            "coverage_analysis.topic_data_unavailable",
            "coverage_analysis.publisher_ranking_unavailable",
            "coverage_analysis.daily_activity_unavailable",
            "coverage_analysis.item",
            "coverage_analysis.items",
            "coverage_analysis.publisher_word",
            "coverage_analysis.publishers_word",
            "coverage_analysis.active_day",
            "coverage_analysis.active_days",
            "coverage_analysis.publisher_represented",
            "coverage_analysis.publishers_represented",
            "coverage_analysis.daily_total",
            "coverage_analysis.daily_report",
            "coverage_analysis.daily_reports",
            "coverage_analysis.untitled_topic",
            "coverage_analysis.unknown_publisher",
        }

        for key in required:
            marker = '"' + key + '":'
            self.assertIn(marker, CATALOG_TEXT)
            self.assertIn(marker, FR_CATALOG_TEXT)

    def test_first_static_text_batch_is_keyed(self):
        targets = {
            "dashboard.what_changed": "WHAT CHANGED",
            "dashboard.race_at_a_glance": "RACE AT A GLANCE",
            "media_pulse.subtitle": (
                "30-day activity · 14-day recent"
            ),
        }

        self.assertEqual(len(targets), 3)

        for key, english in targets.items():
            self.assertEqual(
                INDEX_TEXT.count(f'data-i18n="{key}"'),
                1,
            )
            self.assertEqual(INDEX_TEXT.count(english), 1)

        for retired_loading_key in (
            "dashboard.source_linked_updates_loading",
            "dashboard.checking_for_source_linked_dashboard_signals",
            "dashboard.loading_candidate_scores",
            "dashboard.loading_media_metrics",
        ):
            self.assertNotIn(
                f'data-i18n="{retired_loading_key}"',
                INDEX_TEXT,
            )

    def test_first_static_aria_batch_is_keyed(self):
        targets = {
            "dashboard.first_round_election_countdown": (
                "First-round election countdown"
            ),
            "dashboard.top_briefing": "Top briefing",
            "dashboard.latest_first_round_poll_events": (
                "Latest first-round poll events"
            ),
            "dashboard.choose_a_reported_first_round_poll_scenario": (
                "Choose a reported first-round poll scenario"
            ),
            "dashboard.dashboard_context": "Dashboard context",
        }

        self.assertEqual(len(targets), 5)

        for key, english in targets.items():
            self.assertEqual(
                INDEX_TEXT.count(
                    f'data-i18n-aria-label="{key}"'
                ),
                1,
            )
            self.assertEqual(
                INDEX_TEXT.count(f'aria-label="{english}"'),
                1,
            )

    def test_static_markers_own_only_their_marked_value(self):
        french = run_runtime_harness(
            "https://example.test/dashboard/#signal-candidates"
        )
        english = run_runtime_harness(
            "https://example.test/dashboard/?lang=en#signal-candidates"
        )

        self.assertEqual(french["staticText"], "Texte français actif")
        self.assertEqual(french["staticAria"], "Libellé français actif")
        self.assertEqual(
            french["staticTooltip"],
            "Infobulle française active",
        )
        self.assertEqual(english["staticText"], "English catalog text")
        self.assertEqual(english["staticAria"], "English catalog label")
        self.assertEqual(
            english["staticTooltip"],
            "English catalog tooltip",
        )

        self.assertEqual(french["pollMetaText"], "Ipsos · Ifop")
        poll_meta_tag = re.search(
            r'<div\b[^>]*\bid="context-poll-meta"[^>]*>',
            INDEX_TEXT,
        )
        self.assertIsNotNone(poll_meta_tag)
        self.assertNotIn("data-i18n=", poll_meta_tag.group(0))
        self.assertIn("data-i18n-fr27-tooltip=", poll_meta_tag.group(0))

    def test_footer_metric_labels_preserve_runtime_values_in_both_locales(self):
        metric_values = {
            "media_pulse.metric.accepted_news": 9127,
            "media_pulse.metric.publishers": 43,
            "media_pulse.metric.recent_14d": 806,
            "media_pulse.metric.candidate_watch": 319,
        }
        footer_value_ids = {
            "media_pulse.metric.accepted_news": "fr27-hud-news-value",
            "media_pulse.metric.publishers": "fr27-hud-publishers-value",
            "media_pulse.metric.recent_14d": "fr27-hud-recent-value",
            "media_pulse.metric.candidate_watch": "fr27-hud-candidate-watch-value",
        }

        render_start = HYBRID_TEXT.index(
            "function renderTopMediaPulse"
        )
        render_end = HYBRID_TEXT.index(
            "function resolveSignalViewFromHash",
            render_start,
        )
        metric_renderer = HYBRID_TEXT[render_start:render_end]
        self.assertIn(
            'data-media-pulse-metric="${escapeAttribute(metric.key)}"',
            metric_renderer,
        )

        for key, value_id in footer_value_ids.items():
            self.assertIn(f'key: "{key}"', metric_renderer)
            value_tag = re.search(
                rf'<strong\b[^>]*\bid="{re.escape(value_id)}"[^>]*>',
                INDEX_TEXT,
            )
            self.assertIsNotNone(value_tag)
            self.assertNotIn("data-i18n=", value_tag.group(0))

        locale_cases = {
            "fr": (
                "https://example.test/",
                {
                    "media_pulse.metric.accepted_news": "éléments retenus",
                    "media_pulse.metric.publishers": "médias",
                    "media_pulse.metric.recent_14d": "récent (14 j)",
                    "media_pulse.metric.candidate_watch": "suivi candidats",
                },
            ),
            "en": (
                "https://example.test/?lang=en",
                {
                    "media_pulse.metric.accepted_news": "accepted news",
                    "media_pulse.metric.publishers": "publishers",
                    "media_pulse.metric.recent_14d": "recent (14d)",
                    "media_pulse.metric.candidate_watch": "candidate-watch",
                },
            ),
        }

        for locale, (href, labels) in locale_cases.items():
            with self.subTest(locale=locale):
                metrics = [
                    {
                        "key": key,
                        "value": value,
                        "label": labels[key],
                    }
                    for key, value in metric_values.items()
                ]
                result = run_footer_harness(href, metrics)

                self.assertEqual(result["footerLabels"], labels)
                self.assertEqual(
                    result["footerValues"],
                    {
                        footer_value_ids[key]: str(value)
                        for key, value in metric_values.items()
                    },
                )

    def test_catalog_and_explicit_caller_fallback_behavior(self):
        result = run_runtime_harness(
            "http://localhost/dashboard/#signal-candidates"
        )

        self.assertEqual(
            result["englishCatalogFallback"],
            "English fallback for Camille",
        )
        self.assertEqual(
            result["legacyParameterizedCall"],
            "English fallback for Alex",
        )
        self.assertEqual(
            result["callerInterpolation"],
            "Fallback for Camille",
        )
        self.assertEqual(result["callerPluralOne"], "record: 1")
        self.assertEqual(result["callerPluralOther"], "records: 2")
        self.assertEqual(
            result["finalDiagnostic"],
            "missing.no_fallback",
        )

        warned_keys = [warning[-1] for warning in result["warnings"]]
        self.assertIn("missing.interpolation", warned_keys)
        self.assertIn("missing.plural.one", warned_keys)
        self.assertIn("missing.plural.other", warned_keys)
        self.assertIn("missing.no_fallback", warned_keys)

    def test_unmarked_source_evidence_is_unchanged(self):
        result = run_runtime_harness(
            "https://example.test/dashboard/#signal-candidates"
        )
        self.assertEqual(
            result["sourceEvidence"],
            [
                "Titre de source",
                "Le Monde",
                "parrainage",
                "Ipsos · Ifop",
            ],
        )


    def test_static_shell_context_batch_is_keyed(self):
        targets = {
            "dashboard.source_linked_signals_from_the_french_presidential_race": (
                "Source-linked signals from the French presidential race."
            ),
            "dashboard.next_milestone": "NEXT MILESTONE",
            "dashboard.latest_fieldwork": "LATEST FIELDWORK",
            "dashboard.poll_coverage": "POLL COVERAGE",
            "dashboard.source_network": "SOURCE NETWORK",
        }

        self.assertEqual(len(targets), 5)

        for key, english in targets.items():
            self.assertEqual(
                INDEX_TEXT.count(f'data-i18n="{key}"'),
                1,
            )
            self.assertEqual(
                INDEX_TEXT.count(english),
                1,
            )

    def test_poll_semantics_copy_is_catalogued(self):
        messages = catalog_messages()
        self.assertEqual(
            messages["dashboard.vs_prior_match"],
            "VS PRIOR MATCH",
        )
        self.assertEqual(
            messages["dashboard.vs_prior_match_explanation"],
            "Nearest earlier poll from the same pollster testing the same candidate field.",
        )
        self.assertEqual(
            messages["dashboard.latest_fieldwork_explanation"],
            "Maximum fieldwork end date across published first-round poll events; all pollsters tied on that date are shown.",
        )
        self.assertIn(
            'data-i18n-fr27-tooltip="dashboard.latest_fieldwork_explanation"',
            INDEX_TEXT,
        )


    def test_javascript_generated_headings_use_localization_fallbacks(self):
        adapters = (
            (
                ROOT / "assets" / "election-coverage-modal.js",
                "\n\n  const state =",
            ),
            (
                ROOT / "assets" / "hybrid-dashboard.js",
                "\n\n  const renderStrongDateOrUnavailable",
            ),
            (
                ROOT / "assets" / "topic-coverage-modal.js",
                "\n\n  const collator =",
            ),
        )

        for path, end_marker in adapters:
            with self.subTest(path=path.name):
                result = run_adapter_harness(path, end_marker)
                self.assertEqual(
                    result["result"],
                    "Adapter fallback {count}",
                )
                self.assertEqual(
                    result["calls"],
                    [
                        {
                            "key": "missing.adapter.key",
                            "parameters": {"count": 2},
                            "fallback": "Adapter fallback {count}",
                        }
                    ],
                )

        hybrid_text = (
            ROOT / "assets" / "hybrid-dashboard.js"
        ).read_text(
            encoding="utf-8-sig",
            errors="strict",
        )
        candidate_text = (
            ROOT / "assets" / "candidate-signals-workspace.js"
        ).read_text(
            encoding="utf-8-sig",
            errors="strict",
        )

        expected_calls = {
            hybrid_text: (
                'translate("signal_board.runoff", "RUNOFF")',
                'translate("signal_board.candidates_847367c6", "CANDIDATES")',
                'translate("signal_board.closest_runoff", "Closest Runoff")',
                'translate("signal_board.candidate_signals", "Candidate Signals")',
                'translate("signal_board.campaign_events", "Campaign Events")',
                'translate("signal_board.campaign_agenda", "Campaign Agenda")',
            ),
            candidate_text: (
                'translate('
                '"candidate.candidate_monitor", '
                '"CANDIDATE MONITOR"'
                ')',
                'translate('
                '"candidate.selected_analysis", '
                '"SELECTED ANALYSIS"'
                ')',
                'translate('
                '"candidate.candidate_dossier", '
                '"CANDIDATE DOSSIER"'
                ')',
            ),
        }

        for source, calls in expected_calls.items():
            for call in calls:
                self.assertEqual(
                    source.count(call),
                    1,
                )

    def test_candidate_scrutiny_archive_by_uses_localization(self):
        candidate_text = (
            ROOT / "assets" / "candidate-signals-workspace.js"
        ).read_text(
            encoding="utf-8-sig",
            errors="strict",
        )

        call = (
            'translate('
            '"candidate.scrutiny.archive_by", '
            '"Archive · BY"'
            ')'
        )

        self.assertEqual(
            candidate_text.count(call),
            2,
        )
        self.assertEqual(
            candidate_text.count(
                '["Archive · BY",'
            ),
            0,
        )

        for start_marker in (
            "function scrutinyLines(candidate) {",
            "function dossierScrutinyLines(candidate) {",
        ):
            start = candidate_text.index(
                start_marker
            )
            body_start = (
                start + len(start_marker)
            )
            next_function = candidate_text.find(
                "\n  function ",
                body_start,
            )
            end = (
                len(candidate_text)
                if next_function < 0
                else next_function
            )
            block = candidate_text[start:end]
            self.assertEqual(
                block.count(call),
                1,
            )

    def test_inline_dynamic_messages_use_localization_seam(self):
        index_text = (
            ROOT / "index.html"
        ).read_text(
            encoding="utf-8-sig",
            errors="strict",
        )

        adapter = (
            "const translate = "
            "(key, fallback, parameters) => {\n"
            "      const localizer = globalThis.FR27I18N;\n"
            "      return localizer && "
            'typeof localizer.t === "function"\n'
            "        ? localizer.t(key, parameters)\n"
            "        : fallback;\n"
            "    };"
        )

        self.assertEqual(
            index_text.count(adapter),
            1,
        )
        self.assertEqual(
            index_text.count(
                "const candidatePortraitAlt = "
                "candidateName =>"
            ),
            1,
        )

        for key in (
            "dashboard.candidate_portrait_alt",
            "dashboard.claims.review_count_label",
            "dashboard.news.campaign_agenda_unavailable",
            "dashboard.news.candidate_coverage_unavailable",
            "dashboard.news.relevant_news_unavailable",
            "dashboard.poll.partial_reported_field",
            "dashboard.runoff.smallest_reported_margin",
            "dashboard.source.open_category_source_from_publisher",
        ):
            self.assertEqual(
                index_text.count(f'"{key}"'),
                1,
            )

        self.assertEqual(
            index_text.count(
                "candidatePortraitAlt("
            ),
            6,
        )
        self.assertEqual(
            index_text.count(
                "image.alt = "
                "candidatePortraitAlt(candidateName);"
            ),
            1,
        )
        self.assertEqual(
            index_text.count(
                "escapeAttribute("
                "candidatePortraitAlt(candidateName))"
            ),
            4,
        )
        self.assertEqual(
            index_text.count(
                "escapeAttribute("
                "candidatePortraitAlt(name))"
            ),
            1,
        )
        self.assertEqual(
            index_text.count(
                'image.alt = "AI-generated portrait of " '
                "+ candidateName;"
            ),
            0,
        )
        self.assertEqual(
            index_text.count(
                "const errorMessage = "
                "escapeHtml(error.message);"
            ),
            1,
        )
        self.assertEqual(
            index_text.count(
                "{ errorMessage }"
            ),
            3,
        )
        self.assertEqual(
            index_text.count(
                "{ reportedTotal, "
                "unreportedShare }"
            ),
            1,
        )

    def test_hybrid_dynamic_date_messages_are_parameterized(self):
        hybrid_text = (
            ROOT / "assets" / "hybrid-dashboard.js"
        ).read_text(
            encoding="utf-8-sig",
            errors="strict",
        )

        self.assertEqual(
            hybrid_text.count(
                "const renderStrongDateOrUnavailable = ("
            ),
            1,
        )
        self.assertIn(
            "localizer.formatDate(value, options)",
            hybrid_text,
        )
        self.assertIn(
            '"coverage_modal.unavailable"',
            hybrid_text,
        )
        self.assertIn(
            (
                "return `<strong>"
                "${escapeHtml(renderedValue)}"
                "</strong>`;"
            ),
            hybrid_text,
        )

        for key in (
            "signal_board.media.latest_accepted_item",
        ):
            self.assertEqual(
                hybrid_text.count(f'"{key}"'),
                1,
            )

        self.assertEqual(
            hybrid_text.count(
                "dateOrUnavailable: latestAcceptedValue"
            ),
            1,
        )
        self.assertIn(
            'timeZone: "Europe/Paris"',
            hybrid_text,
        )
        self.assertIn(
            'timeZone: "UTC"',
            hybrid_text,
        )



if __name__ == "__main__":
    unittest.main()
