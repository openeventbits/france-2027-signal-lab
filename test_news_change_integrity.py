"""Frozen evidence and semantic guards for material news-ledger promotion.

These minimal source rows preserve the two reviewed articles' original feed
identity. They intentionally do not depend on a moving production news window.
Publisher pages document the historical campaign and interview respectively;
their timestamps do not replace the feed dates stored in the news corpus.
"""

from __future__ import annotations

import copy
import json
import unittest

from fetch_news_wire import classify_structured_electoral_support, normalize
from generate_recent_changes import (
    classify_news_change,
    compose_recent_changes,
    parse_datetime,
)


REVIEW_CLOCK = parse_datetime("2026-10-28T16:23:06.102187Z")

# TF1 identifies original publication on 2017-02-01 and an update on
# 2026-09-24. Neither establishes the origin of this Google News feed date.
# https://www.tf1info.fr/politique/elections/presidentielle/presidentielles-2017-nicolas-dupont-aignan-devoile-son-programme-2024438.html
DUPONT_AIGNAN_2017 = {
    "id": "c491c4023d07b5c39aee",
    "publisher": "TF1 Info",
    "published_at": "2026-10-24T06:00:57Z",
    "headline": "Présidentielles 2017 : Nicolas Dupont-Aignan dévoile son programme",
    "url": (
        "https://news.google.com/rss/articles/"
        "CBMi0AFBVV95cUxNRTQ1RXBoUlEzVXZGZnVFNzJHLU91LU1fZ2NHZW1DQWJLRWFVNHZ1"
        "LU5NSlR6VWpyVTBuV0gtZE5IUFRnOU9Kb0VldFhkN3JaVTNTazI1WmVubXh0ZVNZMHI2"
        "Q0pBS0xYRU5jR2hCYjB3dkdVQW9LelhCMW5ObUozR09kQ1JTQmhnRFFBM2tMRTNlN0Jx"
        "alJTY3o1WFlYZVFwbllycjFROXJsdFpjSThLd191TnVVcVJybGRyT1RlS2Q1TUNydmcyQ0"
        "ZZTldVYUVn?oc=5"
    ),
    "explicit_election": False,
    "candidates": ["Nicolas Dupont-Aignan"],
    "candidate_matches": [
        {
            "candidate": "Nicolas Dupont-Aignan",
            "matched_aliases": ["dupont aignan", "nicolas dupont aignan"],
            "locations": ["headline", "summary"],
        }
    ],
    "development_category": "positioning_integrity",
    "development_label": "Positioning & political image",
    "matched_terms": ["devoile son programme"],
}

# The publisher describes a long-form interview about political engagement.
# https://www.lemediatv.fr/emissions/2026/palestine-fascisme-soutien-a-lfi-habibitch-une-artiste-qui-refuse-de-se-taire-6CTF8SDOT6aJ5YUxnz26IQ
HABIBITCH_INTERVIEW = {
    "id": "27cf429402355764ab69",
    "publisher": "Le Média",
    "published_at": "2026-10-27T07:00:00Z",
    "headline": (
        "Palestine, fascisme, soutien à LFI : Habibitch, une artiste qui refuse de se taire"
    ),
    "url": (
        "https://news.google.com/rss/articles/"
        "CBMi1wFBVV95cUxOVGtyam1wYVVya1hOSTBDbFN3ME94LWNFMTZ4MmRaUlkwejNQQ3RFOHI4"
        "S0JicFB1Y1BiLUxreS1tN3MxOS1KQlJYaGdjbFhMeGhtTkw2Y3pVM2JGZjAyTkctS09BUn"
        "lpZG9tNDh5Mk80YkxQVVFFdjFMNG1jTkpwSkU5YUZWS2VaNFZMVVFRSzhNSjBnbk9DU3NK"
        "dGE3ZW8wS2dNc1NvUnA3cDR0dXBTVXVVWVRsMU96VllVNkMxLWJ6VHFOZER0blB2ODNMaU"
        "FDRjJoVVZVQQ?oc=5"
    ),
    "explicit_election": False,
    "candidates": [],
    "candidate_matches": [],
    "development_category": "candidacies_endorsements",
    "development_label": "Candidacies & endorsements",
    "matched_terms": ["electoral_support"],
}

FALSE_LEDGER_IDS = {
    "campaign-c491c4023d07b5c39aee",
    "campaign-27cf429402355764ab69",
}


def article(identifier, headline, *, candidates=(), published_at="2026-10-26T10:00:00Z"):
    return {
        "id": identifier,
        "publisher": "Reviewed publisher",
        "published_at": published_at,
        "headline": headline,
        "url": f"https://example.test/{identifier}",
        "candidates": list(candidates),
        "explicit_election": False,
        "summary": "",
    }


def compose(news, previous=None):
    return compose_recent_changes(
        news=news,
        polls=[],
        runoff={"status": "insufficient"},
        second_round={"events": []},
        claims={"reviews": []},
        previous=previous or {},
        checked_at=REVIEW_CLOCK,
    )


class NewsChangeIntegrityTests(unittest.TestCase):
    def test_actual_feed_rows_are_not_material_changes(self):
        for frozen in (DUPONT_AIGNAN_2017, HABIBITCH_INTERVIEW):
            with self.subTest(source_id=frozen["id"]):
                self.assertIsNone(classify_news_change(copy.deepcopy(frozen)))

    def test_upstream_flags_and_rss_summary_cannot_rescue_false_promotions(self):
        for frozen in (DUPONT_AIGNAN_2017, HABIBITCH_INTERVIEW):
            for explicit_election in (False, True):
                item = copy.deepcopy(frozen)
                item["explicit_election"] = explicit_election
                item["summary"] = (
                    "Présidentielle 2027 : le parti annonce son soutien à LFI et "
                    "Nicolas Dupont-Aignan annonce sa candidature."
                )
                with self.subTest(source_id=item["id"], flag=explicit_election):
                    self.assertIsNone(classify_news_change(item))

    def test_interview_still_has_upstream_support_evidence(self):
        # The permissive shared classifier serves other news surfaces. The
        # stricter material-change boundary must not erase that source evidence.
        evidence = classify_structured_electoral_support(
            normalize(HABIBITCH_INTERVIEW["headline"]), []
        )
        self.assertIn("electoral_support", evidence["matched_terms"])
        self.assertEqual(HABIBITCH_INTERVIEW["candidates"], [])

    def test_fresh_feed_date_does_not_make_prior_campaign_label_current(self):
        cases = [
            "Présidentielles 2017 : Nicolas Dupont-Aignan dévoile son programme",
            "Présidentielle 2022 : le candidat dévoile son programme",
            "PRÉSIDENTIELLE 2017: le candidat annonce sa candidature",
            "Élection présidentielle de 2022 — Nicolas Dupont-Aignan lance sa campagne",
        ]
        for headline in cases:
            item = article("historical", headline, candidates=["Nicolas Dupont-Aignan"])
            item["published_at"] = "2026-10-28T15:00:00Z"
            item["explicit_election"] = True
            with self.subTest(headline=headline):
                self.assertIsNone(classify_news_change(item))

    def test_fresh_2027_actions_may_reference_2017(self):
        cases = [
            "Présidentielle 2027 : Nicolas Dupont-Aignan dévoile son programme, dix ans après 2017",
            "Après son résultat de 2017, Nicolas Dupont-Aignan annonce sa candidature pour 2027",
            "Présidentielle 2027 : le parti présente son programme après les scrutins de 2017 et 2022",
        ]
        for headline in cases:
            with self.subTest(headline=headline):
                result = classify_news_change(
                    article("fresh-reference", headline, candidates=["Nicolas Dupont-Aignan"])
                )
                self.assertIsNotNone(result)
                self.assertEqual(result[0], "campaign")

    def test_nominal_party_support_in_cultural_profiles_is_not_a_new_action(self):
        headlines = [
            "Art, féminisme et soutien au PS : portrait d’une artiste engagée",
            "Un artiste évoque son soutien au RN dans un entretien",
            "Culture et soutien à LFI : entretien avec une artiste",
        ]
        for headline in headlines:
            for explicit_election in (False, True):
                item = article("cultural-profile", headline)
                item["explicit_election"] = explicit_election
                item["summary"] = "Présidentielle 2027 : le parti annonce son soutien au candidat."
                with self.subTest(headline=headline, flag=explicit_election):
                    self.assertIsNone(classify_news_change(item))

    def test_material_party_endorsements_do_not_require_monitored_candidate(self):
        headlines = [
            "Le mouvement annonce son soutien à LFI",
            "Le mouvement apporte son soutien au RN",
            "Le collectif officialise son soutien au PS pour la présidentielle 2027",
            "Le parti apporte son soutien au candidat",
            "Un collectif se rallie au RN",
            "Le soutien du collectif au PS pour la présidentielle 2027",
            "Présidentielle 2027 : un collectif appelle à voter pour LFI",
            "Présidentielle 2027 : un collectif appelle à voter pour le RN",
            "Présidentielle 2027 : un collectif appelle à voter pour le PS",
        ]
        for headline in headlines:
            item = article("party-endorsement", headline)
            with self.subTest(headline=headline):
                self.assertEqual(item["candidates"], [])
                result = classify_news_change(item)
                self.assertIsNotNone(result)
                self.assertEqual(result[0], "campaign")

    def test_named_candidate_noun_endorsements_remain_material(self):
        cases = [
            (
                "Le soutien de François Hollande à la candidature de Raphaël Glucksmann",
                ["François Hollande", "Raphaël Glucksmann"],
            ),
            (
                "Le soutien d’Elon Musk au RN relance la campagne de Marine Le Pen",
                ["Marine Le Pen"],
            ),
        ]
        for headline, candidates in cases:
            with self.subTest(headline=headline):
                result = classify_news_change(article("candidate-support", headline, candidates=candidates))
                self.assertIsNotNone(result)
                self.assertEqual(result[0], "campaign")

    def test_legal_and_presidential_procedure_actions_remain_eligible(self):
        cases = [
            ("Marine Le Pen dépose plainte après la diffusion d’une fausse vidéo", ["Marine Le Pen"]),
            ("Présidentielle 2027 : le Conseil constitutionnel modifie les règles de parrainage", []),
            ("Présidentielle 2017 : Marine Le Pen est condamnée dans le dossier des comptes de campagne", ["Marine Le Pen"]),
            ("Présidentielle française de 2017 : le Conseil constitutionnel rejette le recours sur les comptes de campagne", []),
        ]
        for headline, candidates in cases:
            with self.subTest(headline=headline):
                result = classify_news_change(article("legal-change", headline, candidates=candidates))
                self.assertIsNotNone(result)
                self.assertEqual(result[0], "legal")

    def test_repeated_regeneration_preserves_every_unaffected_object_and_input(self):
        accepted = [
            article(
                "fresh-candidacy", "Présidentielle 2027 : Édouard Philippe annonce sa candidature",
                candidates=["Édouard Philippe"], published_at="2026-10-26T10:00:00Z",
            ),
            article(
                "fresh-candidacy-supporting", "Présidentielle 2027 : Édouard Philippe annonce sa candidature",
                candidates=["Édouard Philippe"], published_at="2026-10-26T11:00:00Z",
            ),
            article(
                "party-vote", "Présidentielle 2027 : le collectif appelle à voter pour LFI",
                published_at="2026-10-25T09:00:00Z",
            ),
            article(
                "candidate-lawsuit", "Marine Le Pen dépose plainte après la diffusion d’une fausse vidéo",
                candidates=["Marine Le Pen"], published_at="2026-10-25T12:00:00Z",
            ),
            article(
                "presidential-procedure", "Présidentielle 2027 : le Conseil constitutionnel modifie les règles de parrainage",
                published_at="2026-10-23T14:00:00Z",
            ),
        ]
        accepted[1]["publisher"] = "Supporting publisher"
        control_news = {
            "generated_at": "2026-10-28T16:00:00Z",
            "election_news": accepted,
            "notable_developments": [],
            "candidate_watch": [],
        }
        baseline = compose(control_news)
        self.assertEqual(baseline["counts"], {
            "total": 4, "campaign": 2, "fact_check": 0, "legal": 2, "polling": 0, "runoff": 0,
        })
        prior = {item["id"]: copy.deepcopy(item) for item in baseline["items"]}
        for item in prior.values():
            item["detected_at"] = "2026-10-26T14:15:00Z"
        for identifier in FALSE_LEDGER_IDS:
            prior[identifier] = {"id": identifier, "detected_at": "2026-10-27T08:00:00Z"}
        expected = compose(control_news, prior)
        news = copy.deepcopy(control_news)
        news["notable_developments"] = [copy.deepcopy(DUPONT_AIGNAN_2017), copy.deepcopy(HABIBITCH_INTERVIEW)]
        news["candidate_watch"] = [copy.deepcopy(DUPONT_AIGNAN_2017)]
        # The ledger must leave all upstream surface evidence untouched.
        news["relevant_news"] = [copy.deepcopy(HABIBITCH_INTERVIEW)]
        news["candidate_visibility"] = {"reviewed_fixture": ["unchanged"]}
        news["campaign_agenda"] = {"reviewed_fixture": ["unchanged"]}
        before_news = copy.deepcopy(news)
        before_prior = copy.deepcopy(prior)

        corrected = compose(news, prior)
        repeated = compose(news, prior)
        replayed = compose(news, {item["id"]: item for item in corrected["items"]})

        self.assertEqual(corrected["items"], expected["items"])
        self.assertEqual(corrected["counts"], expected["counts"])
        self.assertEqual(corrected["diagnostics"]["omitted_news_non_material"], 2)
        self.assertFalse(FALSE_LEDGER_IDS & {item["id"] for item in corrected["items"]})
        supporting = next(item for item in corrected["items"] if item["id"] == "campaign-fresh-candidacy")
        self.assertEqual(supporting["supporting_source_count"], 1)
        self.assertEqual(supporting["supporting_sources"][0]["url"], accepted[1]["url"])
        self.assertTrue(all(item["detected_at"] == "2026-10-26T14:15:00Z" for item in corrected["items"]))
        serialize = lambda payload: json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.assertEqual(serialize(corrected), serialize(repeated))
        self.assertEqual(serialize(corrected), serialize(replayed))
        self.assertEqual(news, before_news)
        self.assertEqual(prior, before_prior)


if __name__ == "__main__":
    unittest.main()
