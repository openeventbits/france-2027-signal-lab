from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent
HYBRID = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")


def catalog(locale: str) -> dict[str, str]:
    source = (ROOT / "locales" / f"{locale}.js").read_text(encoding="utf-8")
    match = re.search(
        r"const messages = Object\.freeze\((\{.*?\})\);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"{locale} catalog was not found")
    return json.loads(match.group(1))


def semantic_payload() -> dict:
    event = {
        "event_id": "event-source-identity",
        "event_type": "debate",
        "title": "Débat citoyen — titre publié",
        "candidate_ids": ["candidate-elodie", "candidate-mael"],
        "candidate_names": ["Élodie Martin", "Maël Dubois"],
        "participants": ["Élodie Martin", "Maël Dubois"],
        "organization": "Mouvement Exemple",
        "location_name": "Salle des Fêtes",
        "locality": "Lyon",
        "department": "69",
        "scheduled_start": "2026-09-14T18:30:00+02:00",
        "time_precision": "datetime",
        "timezone": "Europe/Paris",
        "status": "scheduled",
        "evidence_status": "verified",
        "last_verified_at": "2026-09-08T08:15:00Z",
        "evidence": [
            {
                "source_url": "https://example.test/calendrier?preuve=brute",
                "source_publisher": "Agence Démonstration",
                "source_type": "reliable_media",
                "evidence_type": "explicit_schedule",
            }
        ],
    }
    updates = []
    for index, update_type in enumerate(
        ("NEW", "CONFIRMED", "UPDATED", "POSTPONED", "CANCELLED")
    ):
        updates.append(
            {
                "update_id": f"update-{index}",
                "event_id": event["event_id"],
                "update_type": update_type,
                "headline": (
                    "Titre de mise à jour publié — à préserver"
                    if update_type == "UPDATED"
                    else f"Manchette source {update_type}"
                ),
                "observed_at": f"2026-09-08T0{index + 3}:00:00Z",
                "evidence": [
                    {
                        "source_url": f"https://example.test/maj/{index}?brut=oui",
                        "source_publisher": "Agence Démonstration",
                        "source_type": "reliable_media",
                        "evidence_type": "explicit_status_update",
                    }
                ],
            }
        )
    return {
        "generated_at": "2026-09-08T10:00:00Z",
        "data_as_of": "2026-09-08T09:59:00Z",
        "campaign_events": [event],
        "institutional_milestones": [],
        "event_watch": updates,
    }


def run_events(locale: str, payload: dict | None = None, load_state: str = "loaded") -> dict:
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("Node.js is required for Events localization tests")
    messages = catalog(locale)
    script = r'''
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const source = fs.readFileSync("assets/hybrid-dashboard.js", "utf8")
  .replace(/\r\n?/g, "\n");
const RealDate = Date;
class FixedDate extends RealDate {
  constructor(...args) {
    super(...(args.length ? args : ["2026-09-08T10:00:00Z"]));
  }
  static now() { return new RealDate("2026-09-08T10:00:00Z").getTime(); }
}
const localeTag = input.locale === "fr" ? "fr-FR" : "en-GB";
const pluralPattern = /\{([A-Za-z0-9_]+),\s*plural,\s*one\s*\{([^{}]*)\}\s*other\s*\{([^{}]*)\}\s*\}/g;
const translate = (key, fallback, parameters = {}) => {
  const message = String(input.messages[key] ?? fallback);
  const pluralized = message.replace(
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
const escape = value => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[character]);
const safeSourceUrl = value => {
  try {
    const url = new URL(String(value));
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch (_error) {
    return "";
  }
};
const context = {
  URL,
  Date: FixedDate,
  Intl,
  Map,
  Set,
  Number,
  String,
  Math,
  JSON,
  Object,
  Array,
  window: {},
  translate,
  escapeHtml: escape,
  escapeAttribute: escape,
  safeSourceUrl,
  sourceLink(url, label, className = "", accessibleLabel = "") {
    const safe = safeSourceUrl(url);
    return safe
      ? `<a class="${className}" href="${escape(safe)}" target="_blank" rel="noopener noreferrer"${accessibleLabel ? ` aria-label="${escape(accessibleLabel)}"` : ""}>${escape(label)} <span aria-hidden="true">↗</span></a>`
      : `<span class="${className}">Source unavailable</span>`;
  },
  campaignEventLocaleTag() { return localeTag; },
  campaignEventUsesEnglishPresentation() { return localeTag.startsWith("en"); },
  utcDateKey(date) { return date.toISOString().slice(0, 10); },
  state: {
    selectedCampaignEventId: "event-source-identity",
    selectedCampaignEventWeekStart: "",
    campaignEventTypeFilter: "all"
  },
  dashboardState: {
    campaignEvents: input.payload,
    loadState: { campaignEvents: input.loadState }
  },
  viewModelState(name) {
    const state = input.loadState;
    if (state === "loading") return { state: "loading", message: "raw loading" };
    if (state === "error") return { state: "unavailable", message: "raw unavailable" };
    if (!input.payload) return { state: "empty", message: "raw empty" };
    return null;
  }
};
context.FR27I18N = {
  locale: input.locale,
  localeTag,
  t(key, parameters, fallback) { return translate(key, fallback, parameters); }
};
context.globalThis = context;
const temporalStart = source.indexOf("  function parisTodayKey(");
const temporalEnd = source.indexOf("\n\n  function safelyBuildViewModel(", temporalStart);
const rendererStart = source.indexOf("  function campaignEventTypeLabel(");
const rendererEnd = source.indexOf("\n\n  function renderFocusWorkspace(models)", rendererStart);
if ([temporalStart, temporalEnd, rendererStart, rendererEnd].some(value => value < 0)) {
  throw new Error("Could not extract live Events implementation");
}
vm.runInNewContext(
  source.slice(temporalStart, temporalEnd) + "\n" +
  source.slice(rendererStart, rendererEnd),
  context
);
const rawBefore = JSON.stringify(input.payload);
const model = context.buildEventsViewModel();
const html = context.renderEventsPanel(model);
const eventTypes = [
  "rally", "debate", "candidate_visit", "campaign_launch",
  "media_appearance", "press_conference", "public_meeting", "speech",
  "party_event", "primary", "candidacy_announcement", "program_launch",
  "other", "sponsorship_deadline", "official_candidate_list",
  "campaign_period_boundary", "first_round", "second_round"
];
const statuses = ["scheduled", "postponed", "cancelled", "completed"];
const updateTypes = ["NEW", "CONFIRMED", "UPDATED", "POSTPONED", "CANCELLED"];
const output = {
  html,
  history: model.selectedUpdates ? context.renderDossierHistory(model) : "",
  rawUnchanged: rawBefore === JSON.stringify(input.payload),
  modelRaw: {
    eventStatus: model.selectedEvent?.status,
    evidenceStatus: model.selectedEvent?.evidence_status,
    updateTypes: (model.eventWatch || []).map(update => update.update_type)
  },
  statuses: Object.fromEntries(statuses.map(status => [
    status,
    context.campaignEventStatusPresentation({ status, evidence_status: "verified" })
  ])),
  pastUnconfirmed: context.campaignEventStatusPresentation({
    status: "scheduled", evidence_status: "past_unconfirmed"
  }),
  evidence: {
    verified: context.campaignEventEvidencePresentation({ evidence_status: "verified" }),
    past_unconfirmed: context.campaignEventEvidencePresentation({ evidence_status: "past_unconfirmed" })
  },
  updateLabels: Object.fromEntries(updateTypes.map(type => [
    type, context.campaignEventUpdateTypeLabel(type)
  ])),
  updateCopies: Object.fromEntries((model.eventWatch || []).map(update => [
    update.update_type, context.campaignEventUpdateCopy(update)
  ])),
  eventTypes: Object.fromEntries(eventTypes.map(type => [
    type, {
      label: context.campaignEventTypeLabel(type),
      display: context.campaignEventTypeDisplayLabel(type),
      code: context.campaignEventTypeCode(type)
    }
  ])),
  sourceTypes: Object.fromEntries([
    "reliable_media", "organizer_first_party", "candidate_first_party",
    "party_first_party", "official_structured", "official_unstructured"
  ].map(type => [type, context.campaignEventSourceTypeLabel(type)])),
  evidenceTypes: Object.fromEntries([
    "explicit_schedule", "explicit_status_update", "official_rule_derivation"
  ].map(type => [type, context.campaignEventEvidenceTypeLabel(type)])),
  horizonLabels: Object.fromEntries([
    "debate", "rally", "visit", "launch", "media", "other"
  ].map(type => [type, context.campaignEventHorizonCategoryLabel(type)])),
  countSamples: {
    participantOne: translate(
      "events_workspace.participant_count",
      "{count} {count, plural, one {PARTICIPANT} other {PARTICIPANTS}}",
      { count: 1 }
    ),
    participantMany: translate(
      "events_workspace.participant_count",
      "{count} {count, plural, one {PARTICIPANT} other {PARTICIPANTS}}",
      { count: 3 }
    ),
    candidateOne: translate(
      "events_workspace.candidate_count",
      "{count} {count, plural, one {CANDIDATE} other {CANDIDATES}}",
      { count: 1 }
    ),
    candidateMany: translate(
      "events_workspace.candidate_count",
      "{count} {count, plural, one {CANDIDATE} other {CANDIDATES}}",
      { count: 3 }
    ),
    additionOne: translate(
      "events_workspace.addition_count",
      "+{count} {count, plural, one {NEW} other {NEW}}",
      { count: 1 }
    ),
    additionMany: translate(
      "events_workspace.addition_count",
      "+{count} {count, plural, one {NEW} other {NEW}}",
      { count: 3 }
    )
  },
  dates: {
    monthShort: context.campaignEventMonthShort("2026-09-08"),
    monthLong: context.campaignEventMonthLong("2026-09-08"),
    week: context.campaignEventWeekRangeLabel("2026-09-07", "2026-09-13"),
    time: context.campaignEventTimeLabel(input.payload?.campaign_events?.[0] || {}),
    observed: context.campaignEventObservedLabel("2026-09-08T08:15:00Z"),
    observedParts: context.campaignEventObservedParts("2026-09-08T08:15:00Z"),
    short: context.campaignEventShortDate("2026-09-14"),
    long: context.campaignEventLongDate("2026-09-14"),
    weekday: context.campaignEventWeekdayLabel("2026-09-14"),
    relative: context.campaignEventRelativeAgeLabel("2026-09-08T08:00:00Z", new FixedDate())
  }
};
process.stdout.write(JSON.stringify(output));
'''
    completed = subprocess.run(
        [node, "-e", script],
        cwd=ROOT,
        input=json.dumps(
            {
                "locale": locale,
                "messages": messages,
                "payload": payload,
                "loadState": load_state,
            }
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


class BatchELocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = semantic_payload()
        cls.fr = run_events("fr", cls.payload)
        cls.en = run_events("en", cls.payload)
        cls.en_catalog = catalog("en")
        cls.fr_catalog = catalog("fr")

    def test_french_live_events_headings_and_core_surfaces(self):
        for expected in (
            "CALENDRIER · 12 SEMAINES",
            "ÉVÉNEMENTS À VENIR",
            "DOSSIER ÉVÉNEMENT",
            "SUIVI DU CALENDRIER",
            "ACTIVITÉ DU CALENDRIER",
            "DÉTAILS DE L’ÉVÉNEMENT",
            "2 PARTICIPANTS",
            "ÉLÉMENTS SOURCÉS",
            "AJOUTS RÉCENTS",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.fr["html"])

    def test_status_and_evidence_labels_derive_from_raw_stable_ids(self):
        expected_statuses = {
            "scheduled": "PROGRAMMÉ",
            "postponed": "REPORTÉ",
            "cancelled": "ANNULÉ",
            "completed": "TERMINÉ",
        }
        self.assertEqual(
            {key: value["label"] for key, value in self.fr["statuses"].items()},
            expected_statuses,
        )
        self.assertEqual(self.fr["pastUnconfirmed"]["label"], "PASSÉ · NON CONFIRMÉ")
        self.assertEqual(self.fr["evidence"]["verified"]["label"], "VÉRIFIÉ")
        self.assertEqual(
            self.fr["evidence"]["past_unconfirmed"]["label"],
            "NON CONFIRMÉ",
        )
        self.assertEqual(self.fr["modelRaw"]["eventStatus"], "scheduled")
        self.assertEqual(self.fr["modelRaw"]["evidenceStatus"], "verified")
        self.assertEqual(
            set(self.fr["modelRaw"]["updateTypes"]),
            {"NEW", "CONFIRMED", "UPDATED", "POSTPONED", "CANCELLED"},
        )

    def test_update_type_presentation_and_copy_are_localized_by_identity(self):
        self.assertEqual(
            self.fr["updateLabels"],
            {
                "NEW": "AJOUT",
                "CONFIRMED": "CONFIRMÉ",
                "UPDATED": "MIS À JOUR",
                "POSTPONED": "REPORTÉ",
                "CANCELLED": "ANNULÉ",
            },
        )
        self.assertEqual(
            self.fr["updateCopies"]["UPDATED"],
            "Titre de mise à jour publié — à préserver",
        )
        for expected in (
            "Ajout d’après Agence Démonstration",
            "Confirmation du calendrier publiée par Agence Démonstration",
            "Report publié par Agence Démonstration",
            "Annulation publiée par Agence Démonstration",
        ):
            self.assertIn(expected, self.fr["updateCopies"].values())
        self.assertIn('data-update-type="updated">MIS À JOUR</span>', self.fr["html"])

    def test_source_derived_values_and_source_url_are_unchanged(self):
        self.assertTrue(self.fr["rawUnchanged"])
        for value in (
            "Débat citoyen — titre publié",
            "Élodie Martin",
            "Maël Dubois",
            "Mouvement Exemple",
            "Salle des Fêtes",
            "Lyon",
            "Agence Démonstration",
        ):
            self.assertIn(value, self.fr["html"])
        source_url = self.payload["campaign_events"][0]["evidence"][0]["source_url"]
        self.assertIn(f'href="{source_url}"', self.fr["html"])
        self.assertIn(
            'aria-label="Ouvrir la source de Débat citoyen — titre publié"',
            self.fr["html"],
        )

    def test_event_type_presentations_are_keyed_without_changing_codes(self):
        expected = {
            "rally": "MEETING",
            "debate": "DÉBAT",
            "candidate_visit": "DÉPLACEMENT",
            "campaign_launch": "LANCEMENT DE CAMPAGNE",
            "media_appearance": "PASSAGE MÉDIATIQUE",
            "press_conference": "CONFÉRENCE DE PRESSE",
            "public_meeting": "RÉUNION PUBLIQUE",
            "speech": "DISCOURS",
            "party_event": "ÉVÉNEMENT PARTISAN",
            "primary": "PRIMAIRE",
            "candidacy_announcement": "ANNONCE DE CANDIDATURE",
            "program_launch": "PRÉSENTATION DU PROGRAMME",
            "other": "AUTRE",
            "sponsorship_deadline": "DATE LIMITE DES PARRAINAGES",
            "official_candidate_list": "LISTE OFFICIELLE DES CANDIDATS",
            "campaign_period_boundary": "JALON DE LA PÉRIODE DE CAMPAGNE",
            "first_round": "PREMIER TOUR",
            "second_round": "SECOND TOUR",
        }
        self.assertEqual(
            {key: value["label"] for key, value in self.fr["eventTypes"].items()},
            expected,
        )
        self.assertEqual(self.fr["eventTypes"]["rally"]["code"], "RL")
        self.assertEqual(self.fr["eventTypes"]["debate"]["code"], "DB")
        self.assertEqual(self.en["eventTypes"]["candidate_visit"]["display"], "Candidate Visit")
        self.assertEqual(self.fr["eventTypes"]["candidate_visit"]["display"], "Déplacement")

    def test_source_evidence_and_horizon_taxonomies_are_localized_by_id(self):
        self.assertEqual(
            self.fr["sourceTypes"],
            {
                "reliable_media": "MÉDIA FIABLE",
                "organizer_first_party": "SOURCE DE L’ORGANISATEUR",
                "candidate_first_party": "SOURCE DU CANDIDAT",
                "party_first_party": "SOURCE DU PARTI",
                "official_structured": "SOURCE OFFICIELLE STRUCTURÉE",
                "official_unstructured": "SOURCE OFFICIELLE",
            },
        )
        self.assertEqual(
            self.fr["evidenceTypes"],
            {
                "explicit_schedule": "Programmation explicitement publiée",
                "explicit_status_update": "Mise à jour explicite du statut publiée",
                "official_rule_derivation": "Déduit du calendrier officiel",
            },
        )
        self.assertEqual(
            self.fr["horizonLabels"],
            {
                "debate": "DÉBAT",
                "rally": "MEETING",
                "visit": "DÉPLACEMENT",
                "launch": "LANCEMENT",
                "media": "MÉDIA",
                "other": "AUTRE",
            },
        )

    def test_dates_are_locale_aware_and_keep_utc_paris_semantics(self):
        self.assertEqual(
            self.fr["dates"],
            {
                "monthShort": "sept.",
                "monthLong": "septembre",
                "week": "7–13 sept.",
                "time": "18:30",
                "observed": "08 sept. 2026 · 10:15",
                "observedParts": {"date": "08 sept. 2026", "time": "10:15"},
                "short": "14 sept.",
                "long": "14 sept. 2026",
                "weekday": "lun.",
                "relative": "IL Y A 2 H",
            },
        )
        self.assertEqual(
            self.en["dates"],
            {
                "monthShort": "SEP",
                "monthLong": "SEPTEMBER",
                "week": "7–13 SEP",
                "time": "18:30",
                "observed": "08 SEPT 2026 · 10:15",
                "observedParts": {"date": "08 SEPT 2026", "time": "10:15"},
                "short": "14 SEPT",
                "long": "14 SEPT 2026",
                "weekday": "MON",
                "relative": "2H AGO",
            },
        )
        observed_parts = HYBRID.split(
            "  function campaignEventObservedParts(value) {", 1
        )[1].split("\n  function campaignEventObservedMinuteKey", 1)[0]
        self.assertNotIn("campaignEventObservedLabel", observed_parts)
        self.assertNotIn('.split(" · ")', observed_parts)
        self.assertIn("Intl.DateTimeFormat", observed_parts)

    def test_counts_empty_loading_and_unavailable_states_are_localized(self):
        self.assertIn("1 ÉVÉNEMENT", self.fr["html"])
        self.assertIn("5 ENTRÉES", self.fr["html"])
        self.assertIn("+1 AJOUT", self.fr["html"])
        self.assertIn("5 ENTRÉES", self.fr["history"])
        self.assertEqual(
            self.fr["countSamples"],
            {
                "participantOne": "1 PARTICIPANT",
                "participantMany": "3 PARTICIPANTS",
                "candidateOne": "1 CANDIDAT",
                "candidateMany": "3 CANDIDATS",
                "additionOne": "+1 AJOUT",
                "additionMany": "+3 AJOUTS",
            },
        )
        empty = run_events("fr", {**self.payload, "campaign_events": [], "event_watch": []})
        no_selection = run_events("fr", {**self.payload, "campaign_events": []})
        no_additions = run_events("fr", {**self.payload, "event_watch": []})
        loading = run_events("fr", self.payload, load_state="loading")
        unavailable = run_events("fr", None, load_state="error")
        self.assertIn("Aucune donnée compatible n’est disponible", empty["html"])
        self.assertIn("Aucun événement à venir", no_selection["html"])
        self.assertIn("Aucun événement de campagne n’est sélectionné", no_selection["html"])
        self.assertIn("AUCUN AJOUT RÉCENT", no_additions["html"])
        self.assertIn("Chargement des événements de campagne", loading["html"])
        self.assertIn("Les données des événements de campagne sont indisponibles", unavailable["html"])

    def test_english_presentation_is_regression_compatible(self):
        for expected in (
            "12-WEEK SCHEDULE",
            "UPCOMING EVENTS",
            "EVENT DOSSIER",
            "SCHEDULE WATCH",
            "SOURCE EVIDENCE",
            "OPEN SOURCE",
            "RALLY / MEETING",
            "+1 NEW",
            "5 RECORDS",
        ):
            self.assertIn(expected, self.en["html"])

    def test_french_fixture_has_no_obvious_app_owned_english(self):
        for english in (
            "12-WEEK SCHEDULE",
            "UPCOMING EVENTS",
            "EVENT DOSSIER",
            "SCHEDULE WATCH",
            "CALENDAR ACTIVITY",
            "SOURCE EVIDENCE",
            "OPEN SOURCE",
            "SCHEDULE HISTORY",
            "MATERIAL CHANGES",
            "RECENT ADDITIONS",
            "RELIABLE MEDIA",
            "Explicit schedule published",
            "No scheduled events",
            "Candidate portraits are AI-generated",
        ):
            with self.subTest(english=english):
                self.assertNotIn(english, self.fr["html"])

    def test_catalog_family_is_semantic_and_complete(self):
        en_keys = {key for key in self.en_catalog if key.startswith("events_workspace.")}
        fr_keys = {key for key in self.fr_catalog if key.startswith("events_workspace.")}
        self.assertEqual(en_keys, fr_keys)
        self.assertGreaterEqual(len(en_keys), 100)
        for key in en_keys:
            self.assertNotRegex(key, r"hybrid|signal-events|event-source-identity")


if __name__ == "__main__":
    unittest.main()
