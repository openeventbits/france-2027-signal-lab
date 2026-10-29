"""10264 documentary publication must never admit a numerical observation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lxml import html

import poll_source_tables as source
import build_poll_pages as pages
import build_poll_explorer as explorer

ROOT = Path(__file__).resolve().parent
EXPECTED = [
    ("Nathalie Arthaud", "1%"), ("Jean-Luc Mélenchon", "16%"),
    ("Fabien Roussel", "2%"), ("Marine Tondelier", "3%"),
    ("Raphaël Glucksmann", "12%"), ("Gabriel Attal", "7%"),
    ("Sébastien Bonnal", "<1%"), ("Édouard Philippe", "15%"),
    ("Bruno Retailleau", "7%"), ("Éric Zemmour", "3%"), ("Marine Le Pen", "34%"),
]

class BonnalDocumentaryPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = source.load_source_tables()
        cls.table = cls.record["tables"]["10264"]["table"]
        cls.payload = json.loads((ROOT / "poll_explorer.json").read_text(encoding="utf-8"))

    def test_original_five_table_records_and_prior_publication_scope_are_preserved(self):
        previous = copy.deepcopy(self.record)
        review = previous.pop("publication_review")
        previous["standalone_pages"].pop("10264")
        self.assertEqual(source.digest(previous), "2210c4943c4984099bf2c217433a8e4d4e0ed656052f5794c1c5c08c473c4737")
        self.assertEqual(review["prior_collection_sha256"], source.digest(previous))
        self.assertEqual(source.digest(self.table), "90fd17b6433f8af12e7fa0cd4914b142e91148e8da8d5e4d5c97e9f1feaacc70")
        self.assertEqual(review["source_record_sha256"], source.digest(self.table))
        self.assertEqual(self.table["source"]["pdf_sha256"], "3e427407804098116e859a47f1ba3b0d0428145714b35c593e900e800768cd27")
        self.assertEqual(self.table["source"]["pdf_page"], 12)

    def test_all_eleven_original_published_results_and_bound_are_exact(self):
        self.assertEqual([(r["published_name"], r["result"]["literal"]) for r in self.table["rows"]], EXPECTED)
        bonnal = next(r for r in self.table["rows"] if r["identity_id"] == "sebastien-bonnal")
        self.assertEqual(bonnal["result"], {"kind":"strict_upper_bound","upper_percent":1,"literal":"<1%"})
        self.assertNotIn("publication_date", self.table)
        self.assertEqual(self.table["numerical_comparisons"], "excluded_whole_table")

    def test_bilingual_page_names_bases_date_precision_and_original_column(self):
        for language in ("fr", "en"):
            with self.subTest(language=language):
                rendered = pages.render_published_source_page("10264", language=language).decode()
                tree = html.fromstring(rendered)
                self.assertEqual([(r.find("th").text_content(), r.find("td").text_content()) for r in tree.xpath("//tbody/tr")], EXPECTED)
                self.assertIn("Sondage OpinionWay pour Sébastien Bonnal" if language == "fr" else "OpinionWay poll for Sébastien Bonnal", tree.xpath("//h1")[0].text_content())
                self.assertIn("Facebook", rendered)
                self.assertIn("2–4 septembre 2026" if language == "fr" else "2–4 September 2026", rendered)
                self.assertIn("date de publication de l’étude n’est pas confirmée" if language == "fr" else "publication date is unconfirmed", rendered)
                self.assertIn("1 034" if language == "fr" else "1,034", rendered)
                self.assertIn("951", rendered)
                self.assertIn("700", rendered)
                self.assertIn("2022", rendered)
                self.assertNotIn("législatives de 2024", rendered)
                self.assertNotIn("2024 legislative", rendered)
                self.assertNotIn("CNEWS", rendered)
                self.assertNotIn("Second tour dans le document", rendered)
                self.assertIn("13%", rendered)
                self.assertIn(self.table["source"]["pdf_url"] + "#page=12", tree.xpath("//a/@href"))

    def test_indexing_navigation_and_canonical_routes_are_separate_from_preview(self):
        for language in ("fr", "en"):
            tree = html.fromstring(pages.render_published_source_page("10264", language=language))
            path = ("/" if language == "fr" else "/en/") + "sondages/documents/opinionway-bonnal-10264/"
            self.assertEqual(tree.xpath('//link[@rel="canonical"]/@href'), ["https://france2027.app" + path])
            self.assertIn("index,follow", tree.xpath('//meta[@name="robots"]/@content')[0])
            self.assertEqual(set(tree.xpath('//link[@rel="alternate"]/@hreflang')), {"fr","en","x-default"})
            self.assertFalse(tree.xpath('//script[@type="application/ld+json"] | //details[starts-with(@id,"scenario-")]'))
            self.assertNotIn("/preview/", html.tostring(tree, encoding="unicode"))

    def test_projection_is_source_only_and_creates_no_numerical_identity(self):
        s = next(s for s in self.payload["source_scenarios"] if s["notice_id"] == "10264")
        self.assertIsNone(s["publication_date"])
        self.assertEqual(s["commissioner"], "Sébastien Bonnal")
        self.assertEqual(s["source_scenario_id"], self.table["source_table_id"])
        self.assertEqual(s["respondent_bases"], {"adults":1034,"registered_voters":951,"certain_to_vote":700})
        self.assertFalse(s["analysis_eligible"])
        self.assertFalse({"event_id","wave_id","scenarios","score"} & s.keys())
        self.assertTrue(all("score" not in c for c in s["candidates"]))
        self.assertNotIn("sebastien-bonnal", {c["candidate_id"] for c in self.payload["candidates"]})

    def test_entire_numerical_read_model_is_independent_of_documentary_projection(self):
        original = explorer.build_poll_explorer(explorer.load_polls(ROOT / "polls.json"))
        with patch.object(explorer, "reviewed_source_scenarios", return_value=[]):
            numeric = explorer.build_poll_explorer(explorer.load_polls(ROOT / "polls.json"))
        self.assertEqual({k:v for k,v in original.items() if k!="source_scenarios"},
                         {k:v for k,v in numeric.items() if k!="source_scenarios"})

    def test_bound_coercion_changed_metadata_and_route_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "source.json"
            for value in (0, 0.5, 1):
                record = copy.deepcopy(self.record)
                row = next(r for r in record["tables"]["10264"]["table"]["rows"] if r["identity_id"]=="sebastien-bonnal")
                row["result"] = {"kind":"exact","percent":value,"literal":str(value)+"%"}
                p.write_text(json.dumps(record),encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "evidence changed"):
                    source.load_source_tables(p)
                with patch.object(source,"RECORD_SHA256",source.digest(record)):
                    with self.assertRaisesRegex(ValueError, "source table changed"):
                        source.load_source_tables(p)
        for mutate in (lambda s:s.update(commissioner="Facebook"),
                       lambda s:s.update(publication_date="2026-09-15"),
                       lambda s:s.update(page_path_fr="/preview/evidence/10264/fr/")):
            sources = copy.deepcopy(self.payload["source_scenarios"])
            mutate(next(s for s in sources if s["notice_id"]=="10264"))
            with self.assertRaises(explorer.PollExplorerError):
                explorer.directory_entries(self.payload["waves"], sources)

    def test_numerical_coverage_warning_is_not_cleared_by_publication(self):
        registry = json.loads((ROOT / "commission_notice_registry.json").read_text(encoding="utf-8"))
        n = next(n for n in registry["notices"] if n["notice_id"]=="commission:10264")
        self.assertEqual(n["coverage"], {"state":"unresolved","matched_event_ids":[],
                                        "method":"reviewed_unrepresentable_bounded_score"})
        manifest = json.loads((ROOT / "publication_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(any("commission:10264" in warning for warning in manifest["warnings"]))

if __name__ == "__main__":
    unittest.main()
