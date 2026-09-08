from pathlib import Path
import json
import re
import subprocess
import unittest

from test_final_dashboard_shell import agenda_evolution_payload
from test_policy_agenda_frontend import policy_payload


ROOT = Path(__file__).resolve().parent
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


LOCALIZED_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
let source = fs.readFileSync("assets/hybrid-dashboard.js", "utf8");
source = source.replace(
  /\s+retainLegacyComparison\(\);\s+renderAll\(\);\s+window\.addEventListener\("hashchange", handleSignalHashChange\);\s+document\.addEventListener\("hybrid:dataset", renderAll\);/,
  ""
);

const pluralPattern =
  /\{([A-Za-z0-9_]+),\s*plural,\s*one\s*\{([^{}]*)\}\s*other\s*\{([^{}]*)\}\s*\}/g;

const applyPluralRules = (message, parameters = {}) =>
  String(message).replace(
    pluralPattern,
    (match, parameterName, oneValue, otherValue) => {
      const numericValue = Number(parameters[parameterName]);
      const localeTag = input.locale === "fr" ? "fr-FR" : "en-GB";
      const category = new Intl.PluralRules(localeTag).select(numericValue);
      return category === "one" ? oneValue : otherValue;
    }
  );

const interpolate = (message, parameters = {}) =>
  String(message).replace(/\{([A-Za-z0-9_]+)\}/g, (match, name) =>
    Object.prototype.hasOwnProperty.call(parameters, name)
      ? String(parameters[name])
      : match
  );
const localizer = {
  locale: input.locale,
  localeTag: input.locale === "fr" ? "fr-FR" : "en-GB",
  t(key, parameters, fallback) {
    const message = input.messages[key] ?? fallback ?? key;
    return interpolate(applyPluralRules(message, parameters), parameters);
  },
  formatNumber(value, options) {
    return new Intl.NumberFormat(this.localeTag, options).format(value);
  }
};
const mount = {};
const windowObject = {
  location: { hash: "" },
  addEventListener() {},
  FR27I18N: localizer
};
const context = {
  console,
  URL,
  Date,
  Math,
  Map,
  Set,
  Object,
  Array,
  Number,
  String,
  JSON,
  Intl,
  FR27I18N: localizer,
  window: windowObject,
  document: {
    getElementById(id) {
      return id === "hybrid-signal-board" ? mount : null;
    },
    addEventListener() {},
    querySelector() { return null; }
  },
  dashboardState: {
    loadState: { news: "ready" },
    news: input.payload
  },
  candidatePortraits: {},
  newestNewsItems: values => values,
  formatScore: value => String(value),
  formatDate: value => String(value),
  escapeHtml: value => String(value),
  escapeAttribute: value => String(value),
  formatNewsDateTime: value => String(value),
  formatRunoffFieldwork: value => String(value),
  safeSourceUrl: value => String(value)
};
vm.runInNewContext(source, context);
const api = context.window.hybridDashboard;
const result = eval(input.expression);
process.stdout.write(JSON.stringify(result));
"""


def run_localized(locale, payload, expression):
    completed = subprocess.run(
        ["node", "-e", LOCALIZED_HARNESS],
        cwd=ROOT,
        input=json.dumps(
            {
                "locale": locale,
                "messages": catalog(locale),
                "payload": payload,
                "expression": expression,
            }
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def batch_payload():
    payload = agenda_evolution_payload()
    policy = policy_payload()["policy_agenda"]
    payload["policy_agenda"] = policy
    return payload


SNAPSHOT_EXPRESSION = r"""(() => {
  const agenda = api.buildAgendaViewModel();
  const issues = api.buildPolicyAgendaViewModel();
  const agendaHtml = api.renderAgendaPanel(agenda);
  const issuesHtml = api.renderIssuesPanel(issues);

  context.dashboardState.loadState.news = "loading";
  const loading = {
    agenda: api.buildAgendaViewModel().message,
    issues: api.buildPolicyAgendaViewModel().message
  };
  context.dashboardState.loadState.news = "error";
  const unavailable = {
    agenda: api.buildAgendaViewModel().message,
    issues: api.buildPolicyAgendaViewModel().message
  };
  context.dashboardState.loadState.news = "ready";
  context.dashboardState.news.campaign_agenda.topics.forEach(
    topic => { topic.display_eligible = false; }
  );
  context.dashboardState.news.policy_agenda.topics.forEach(
    topic => { topic.display_eligible = false; }
  );
  const empty = {
    agenda: api.buildAgendaViewModel().message,
    issues: api.buildPolicyAgendaViewModel().message
  };

  return {
    agendaHtml,
    issuesHtml,
    agendaIds: agenda.evolutionTopics.map(topic => topic.id),
    issueIds: issues.topics.map(topic => topic.id),
    selectedAgendaId: agenda.selectedEvolutionTopic.id,
    selectedIssueId: issues.selectedIssue.id,
    rawAgendaLabels: agenda.evolutionTopics.map(topic => topic.label),
    rawIssueLabels: issues.topics.map(topic => topic.label),
    agendaValues: {
      sourceDays: agenda.selectedEvolutionTopic.source_day_count,
      publishers: agenda.selectedEvolutionTopic.publisher_count,
      change: agenda.selectedEvolutionTopic.agendaShareChangePp
    },
    issueValues: {
      sourceDays: issues.selectedIssue.source_day_count,
      incidence: issues.selectedIssue.latestIncidence,
      change: issues.selectedIssue.incidenceChangePp
    },
    loading,
    unavailable,
    empty
  };
})()"""


class BatchBLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = batch_payload()
        cls.en = run_localized("en", payload, SNAPSHOT_EXPRESSION)
        cls.fr = run_localized("fr", batch_payload(), SNAPSHOT_EXPRESSION)
        cls.en_catalog = catalog("en")
        cls.fr_catalog = catalog("fr")

    def test_french_agenda_shell_vocabulary(self):
        html = self.fr["agendaHtml"]
        for text in (
            "SUIVI DE L’AGENDA",
            "THÈMES ACTIFS",
            "PART TOP 3",
            "ROTATION TOP 3",
            "ÉVOLUTION DE L’AGENDA",
            "COMPARAISON SEMAINES COMPLÈTES",
            "ÉCART HEBDO.",
            "DOSSIER THÉMATIQUE",
            "THÈME RÉCURRENT SÉLECTIONNÉ",
            "ÉVOLUTION DE PART",
            "SIGNAUX ASSOCIÉS",
            "ÉLÉMENTS RÉCENTS",
        ):
            self.assertIn(text, html)

    def test_french_policy_shell_vocabulary(self):
        html = self.fr["issuesHtml"]
        for text in (
            "SUIVI DES ENJEUX",
            "ACTIFS · 7 J",
            "ENJEU DOMINANT",
            "COUVERTURE",
            "ÉVOLUTION DES ENJEUX",
            "DOSSIER ENJEU",
            "ENJEU SÉLECTIONNÉ",
            "INCIDENCE · 7 J",
            "ÉVOLUTION D’INCIDENCE",
            "CANDIDATS ASSOCIÉS",
            "3 occurrences · 1 candidat",
        ):
            self.assertIn(text, html)

    def test_english_shell_remains_unchanged(self):
        for text in (
            "AGENDA MONITOR",
            "ACTIVE TOPICS",
            "AGENDA EVOLUTION",
            "TOPIC DOSSIER",
            "POLICY MONITOR",
            "ACTIVE 7D",
            "ISSUE EVOLUTION",
            "ISSUE DOSSIER",
            "CANDIDATE ASSOCIATIONS",
        ):
            self.assertIn(text, self.en["agendaHtml"] + self.en["issuesHtml"])

    def test_stable_ids_and_raw_model_labels_do_not_change(self):
        for key in (
            "agendaIds",
            "issueIds",
            "selectedAgendaId",
            "selectedIssueId",
            "rawAgendaLabels",
            "rawIssueLabels",
        ):
            self.assertEqual(self.fr[key], self.en[key])
        self.assertIn('data-hybrid-agenda-topic="selection_strategy"', self.fr["agendaHtml"])
        self.assertNotIn('data-hybrid-agenda-topic="Primaires', self.fr["agendaHtml"])
        self.assertIn('data-hybrid-policy-issue="work_purchasing_power_pensions"', self.fr["issuesHtml"])
        self.assertNotIn('data-hybrid-policy-issue="Travail', self.fr["issuesHtml"])

    def test_full_and_compact_taxonomy_labels_resolve_by_id(self):
        self.assertIn("Primaires et stratégies partisanes", self.fr["agendaHtml"])
        self.assertIn("Primaires", self.fr["agendaHtml"])
        self.assertIn("Travail, pouvoir d’achat et retraites", self.fr["issuesHtml"])
        self.assertIn("Travail & pouvoir d’achat", self.fr["issuesHtml"])
        self.assertIn("Retraites", self.fr["issuesHtml"])

    def test_dynamic_values_and_source_evidence_survive(self):
        self.assertEqual(self.fr["agendaValues"], self.en["agendaValues"])
        self.assertEqual(self.fr["issueValues"], self.en["issueValues"])
        for unchanged in (
            "Primaries & party strategy evidence",
            "Publisher A",
            "Présidentielle 2027 : retraites et salaires",
            "Le Monde",
            "Candidate A",
        ):
            self.assertIn(unchanged, self.fr["agendaHtml"] + self.fr["issuesHtml"])

    def test_loading_unavailable_and_empty_states_localize(self):
        self.assertEqual(self.fr["loading"]["agenda"], "Chargement de l’agenda de campagne")
        self.assertEqual(self.fr["loading"]["issues"], "Chargement des enjeux")
        self.assertIn("indisponibles", self.fr["unavailable"]["agenda"])
        self.assertIn("indisponibles", self.fr["unavailable"]["issues"])
        self.assertTrue(self.fr["empty"]["agenda"].startswith("Aucun thème"))
        self.assertTrue(self.fr["empty"]["issues"].startswith("Aucun enjeu"))
        self.assertEqual(self.en["loading"]["agenda"], "Loading campaign agenda")
        self.assertEqual(self.en["loading"]["issues"], "Loading policy issues")

    def test_batch_namespaces_are_complete_in_both_catalogs(self):
        en_keys = {
            key for key in self.en_catalog
            if key.startswith(("agenda_workspace.", "policy_workspace."))
        }
        fr_keys = {
            key for key in self.fr_catalog
            if key.startswith(("agenda_workspace.", "policy_workspace."))
        }
        self.assertEqual(en_keys, fr_keys)
        self.assertEqual(
            {
                key for key in self.en_catalog
                if key.startswith("policy_subtopic.")
            },
            {
                key for key in self.fr_catalog
                if key.startswith("policy_subtopic.")
            },
        )
        dynamic_prefixes = (
            "agenda_workspace.movement.",
            "agenda_workspace.structure.",
            "policy_workspace.code.",
        )
        for key in (
            key for key in en_keys
            if not key.startswith(dynamic_prefixes)
        ):
            self.assertIn(f'"{key}"', HYBRID)
        self.assertIn("`agenda_workspace.${namespace}.${token}`", HYBRID)
        self.assertIn("`policy_workspace.code.${topic.id}`", HYBRID)
        self.assertIn("`policy_subtopic.${String(value || \"\")}`", HYBRID)


if __name__ == "__main__":
    unittest.main()
