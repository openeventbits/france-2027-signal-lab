"""The same notice retains numerical H1/H2 and runoffs alongside documentary H3."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lxml import html
import poll_source_tables as source
import build_poll_explorer as explorer
import build_poll_pages as pages
import build_poll_hub_static_links as hubs

ROOT=Path(__file__).resolve().parent
EXPECTED=[
    ("Nathalie Arthaud","<1%"),("Jean-Luc Mélenchon","17%"),("Fabien Roussel","2%"),
    ("Marine Tondelier","3%"),("Raphaël Glucksmann","9%"),("Karim Bouamrane","<1%"),
    ("Gabriel Attal","7%"),("Édouard Philippe","15%"),("Bruno Retailleau","7%"),
    ("David Lisnard","2%"),("Nicolas Dupont-Aignan","2%"),("Éric Zemmour","2%"),("Marine Le Pen","34%")]
OBSERVATIONS={
    "34b67c973777cf14f9c19068b4642d119367e3312053f442ba16e9612c051cac":"982c06ab3e9bbcada39561b9bca84674d5028f3e69a36a71d43fc79c5bde3ec0",
    "547d14cf13fb2f407e743b91f6347dad9c0a3db48e750b380bdfc27b8fede2cd":"5432011f93502846bd0a02709ecdad5d9e38ca563d06ddfc21621d9715786d1f",
    "74f414c18b471202a9e99991b3aef62a3765aab33af40c333c19c1275ef7cd67":"a0b80d5a1bdf899987747374e567af501ac74548981caee822250ebc3358fd2c",
    "fdf663f564346145574ec28b75f4f9810bc2501065aa6790f9fb014e9148eea4":"724a206992de5c13a36f82ef279f0b0a19174e350e66b452f1db51479c5d0f02"}
def read(name):return json.loads((ROOT/name).read_text(encoding="utf-8"))

class Cnews10260PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record=source.load_source_tables()
        cls.table=cls.record["tables"]["10260"]["table"]
        cls.payload=read("poll_explorer.json")
        cls.entry=next(s for s in cls.payload["source_scenarios"] if s["notice_id"]=="10260")
        cls.wave=next(w for w in cls.payload["waves"] if w["wave_id"]=="wave-5cfde20f50cfb247")

    def test_prior_collection_and_all_five_original_records_remain_authenticated(self):
        before=copy.deepcopy(self.record)
        review=before.pop("publication_review_10260")
        before["standalone_pages"].pop("10260")
        self.assertEqual(source.digest(before),"189049b0d313ee734e316a13e2353acd1853ba21616adbfffd3d4b0458604828")
        self.assertEqual(review["prior_collection_sha256"],source.digest(before))
        self.assertEqual(review["source_record_sha256"],"535cb08075a8c3bb1eb9b8d9ddd0178b7296308872490e546e03c19250369788")
        self.assertEqual(source.digest(self.table),review["source_record_sha256"])
        self.assertEqual(self.table["source_table_id"],"fr27-source-table-v1:13c78f8439b7a6183f043bf9c6cadd0f93e6d3cfb847a2734329240317557b24")
        self.assertEqual(self.table["source"]["pdf_sha256"],"bcc6f5e46048615f31188b9d98cd708339f276e8fe959d3c9c1b5833a1d58b0c")
        self.assertEqual(self.table["source"]["pdf_page"],14)

    def test_all_thirteen_literals_in_source_order_and_both_bounds_are_preserved(self):
        self.assertEqual([(r["published_name"],r["result"]["literal"]) for r in self.table["rows"]],EXPECTED)
        bounds=[r for r in self.table["rows"] if r["result"]["kind"]=="strict_upper_bound"]
        self.assertEqual([r["identity_id"] for r in bounds],["nathalie-arthaud","karim-bouamrane"])
        for row in bounds:self.assertEqual(row["result"],{"kind":"strict_upper_bound","upper_percent":1,"literal":"<1%"})
        self.assertEqual(self.table["numerical_comparisons"],"excluded_whole_table")
        self.assertNotIn("publication_date",self.table)

    def test_all_four_existing_observations_keep_complete_original_objects(self):
        first=read("polls.json");second=read("second_round_polls.json")["events"]
        selected=[e for e in first+second if e["event_id"] in OBSERVATIONS]
        self.assertEqual({e["event_id"]:source.digest(e) for e in selected},OBSERVATIONS)
        self.assertEqual(len(selected),4)
        self.assertEqual({s["event_id"] for s in self.wave["scenarios"]},set(OBSERVATIONS)&{e["event_id"] for e in first})
        self.assertEqual(self.wave["scenario_count"],2)

    def test_h1_h2_and_h3_coexist_under_one_notice_without_a_new_numerical_wave(self):
        entries=explorer.directory_entries(self.payload["waves"],self.payload["source_scenarios"])
        matching=[e for e in entries if e["pollster"]=="OpinionWay" and e["fieldwork_start"]=="2026-09-09" and e["fieldwork_end"]=="2026-09-10"]
        self.assertEqual(len(matching),2)
        self.assertEqual(sum("wave_id" in e for e in matching),1)
        self.assertEqual(sum("source_scenario_id" in e for e in matching),1)
        self.assertEqual(self.entry["survey_id"],"commission:10260")
        self.assertFalse(self.entry["analysis_eligible"])
        self.assertIsNone(self.entry["publication_date"])
        self.assertEqual(self.entry["commissioner"],"CNews")
        self.assertFalse({"event_id","wave_id","scenarios","score","comparison_vector"}&self.entry.keys())
        self.assertTrue(all("score" not in c for c in self.entry["candidates"]))
        self.assertEqual(self.entry["respondent_bases"],{"adults":1001,"registered_voters":935,"certain_to_vote":690})

    def test_bilingual_pages_explain_configuration_dates_bases_weighting_and_runoffs(self):
        for lang in ("fr","en"):
            with self.subTest(language=lang):
                raw=pages.render_published_source_page("10260",language=lang).decode()
                tree=html.fromstring(raw)
                self.assertEqual([(r.find("th").text_content(),r.find("td").text_content()) for r in tree.xpath("//tbody/tr")],EXPECTED)
                self.assertIn("H3",tree.xpath("//h1")[0].text_content())
                self.assertIn("Troisième configuration du premier tour" if lang=="fr" else "Third first-round configuration",raw)
                for term in ("H1","H2","CNews","935","690","15%","2022","2024","p. 15","p. 16"):self.assertIn(term,raw)
                self.assertIn("1 001" if lang=="fr" else "1,001",raw)
                self.assertIn("9–10 septembre 2026" if lang=="fr" else "9–10 September 2026",raw)
                self.assertIn("n’est pas confirmée indépendamment" if lang=="fr" else "not independently confirmed",raw)
                self.assertIn("Non documentée" if lang=="fr" else "Not documented",raw)
                self.assertIn(self.table["source"]["pdf_url"]+"#page=14",tree.xpath("//a/@href"))
                self.assertIn(self.table["source"]["pdf_url"]+"#page=15",tree.xpath("//a/@href"))
                self.assertIn(self.wave["page_path_"+lang],tree.xpath("//a/@href"))
                self.assertIn("H3 : observation numérique absente" if lang=="fr" else "H3: numerical observation absent",raw)

    def test_canonical_alternates_indexing_and_source_section_are_registered(self):
        registry=read("route_registry.json");manifest=read("poll_pages_manifest.json")
        for lang in ("fr","en"):
            path=("" if lang=="fr" else "/en")+"/sondages/documents/opinionway-cnews-10260/"
            tree=html.fromstring(pages.render_published_source_page("10260",language=lang))
            self.assertEqual(tree.xpath('//link[@rel="canonical"]/@href'),["https://france2027.app"+path])
            self.assertEqual(set(tree.xpath('//link[@rel="alternate"]/@hreflang')),{"fr","en","x-default"})
            self.assertIn("index,follow",tree.xpath('//meta[@name="robots"]/@content')[0])
            self.assertFalse(tree.xpath('//script[@type="application/ld+json"] | //details[starts-with(@id,"scenario-")]'))
            self.assertEqual([r["kind"] for r in registry["routes"] if r["path"]==path],["poll-source-evidence"])
            hub=html.fromstring(hubs.HUBS[lang].read_text(encoding="utf-8"))
            links=hub.xpath('//*[@id="source-evidence"]//a[@href="'+path+'"]')
            self.assertEqual(len(links),1);self.assertIn("H3",links[0].text_content())
        self.assertEqual(sum(p["notice_id"]=="10260" for p in manifest["source_pages"]),1)

    def test_entire_numerical_explorer_is_independent_of_source_publication(self):
        all_sources=explorer.build_poll_explorer(read("polls.json"))
        with patch.object(explorer,"reviewed_source_scenarios",return_value=[]):
            numeric=explorer.build_poll_explorer(read("polls.json"))
        self.assertEqual({k:v for k,v in all_sources.items() if k!="source_scenarios"},{k:v for k,v in numeric.items() if k!="source_scenarios"})

    def test_both_bound_coercions_and_altered_source_objects_fail_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"tables.json"
            for candidate in ("nathalie-arthaud","karim-bouamrane"):
                for value in (0,0.5,1):
                    r=copy.deepcopy(self.record)
                    row=next(row for row in r["tables"]["10260"]["table"]["rows"] if row["identity_id"]==candidate)
                    row["result"]={"kind":"exact","percent":value,"literal":str(value)+"%"}
                    p.write_text(json.dumps(r),encoding="utf-8")
                    with self.assertRaisesRegex(ValueError,"evidence changed"):source.load_source_tables(p)
                    with patch.object(source,"RECORD_SHA256",source.digest(r)):
                        with self.assertRaisesRegex(ValueError,"source table changed"):source.load_source_tables(p)
            for mutate in (lambda r:r["tables"]["10260"]["table"]["source"].update(pdf_sha256="0"*64),
                           lambda r:r["standalone_pages"]["10260"].update(page_path_fr="/unauthorized/")):
                r=copy.deepcopy(self.record);mutate(r);p.write_text(json.dumps(r),encoding="utf-8")
                with self.assertRaisesRegex(ValueError,"evidence changed"):source.load_source_tables(p)

    def test_duplicate_h3_wrong_identities_source_dates_and_routes_fail_projection(self):
        for mutate in (lambda s:s.update(commissioner="CNEWS"),lambda s:s.update(survey_id="commission:10319"),
                       lambda s:s.update(publication_date="2026-09-11"),
                       lambda s:s["source"].update(pdf_sha256="0"*64),
                       lambda s:s["candidates"][0].update(candidate_id="someone-else"),
                       lambda s:s.update(page_path_en="/en/unauthorized/"),lambda s:s.update(analysis_eligible=True)):
            entries=copy.deepcopy(self.payload["source_scenarios"]);mutate(next(s for s in entries if s["notice_id"]=="10260"))
            with self.assertRaises(explorer.PollExplorerError):explorer.directory_entries(self.payload["waves"],entries)
        duplicate=copy.deepcopy(self.payload["source_scenarios"])+[copy.deepcopy(self.entry)]
        with self.assertRaisesRegex(explorer.PollExplorerError,"Duplicate"):explorer.directory_entries(self.payload["waves"],duplicate)

    def test_documentary_publication_preserves_the_numerical_coverage_warning(self):
        notice=next(n for n in read("commission_notice_registry.json")["notices"] if n["notice_id"]=="commission:10260")
        self.assertEqual(notice["coverage"],{"state":"unresolved","matched_event_ids":[],"method":"reviewed_incomplete_bounded_score_configuration"})
        self.assertTrue(any("commission:10260" in w for w in read("publication_manifest.json")["warnings"]))

if __name__=="__main__":unittest.main()
