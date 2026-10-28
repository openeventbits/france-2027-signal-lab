"""Authenticated study identity, immutable observations, URLs and homepage eligibility parity."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import build_candidate_signals as signals
import build_poll_explorer as explorer
import build_poll_pages as pages
import poll_studies as studies
import poll_contract as contract

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def run_node(script, value=None):
    result = subprocess.run(["node", "-e", script], cwd=ROOT,
                            input=json.dumps(value), capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


HOMEPAGE_SCRIPT = r'''
const fs = require("fs"), vm = require("vm");
const input = JSON.parse(fs.readFileSync(0,"utf8"));
const source = fs.readFileSync(input.page,"utf8").replace(/\r\n/g,"\n");
const context = {polls:input.polls, result:null};
vm.createContext(context);
vm.runInContext(fs.readFileSync("assets/poll-study-bindings.js","utf8"),context);
let functions = "const raceGlanceState={selectedHypothesisByPoll:{}};\n";
for(const name of ["candidateScore","isValidFirstRoundPollEvent","normalizeComparableText",
  "subtractCalendarMonths","deriveLatestFieldworkSummary","derivePollCoverage","formatComparableDelta","formatComparableChange",
  "deriveComparableChange","raceCandidateField","raceCandidateFieldDistance","raceCandidateFieldChanges",
  "deriveRacePreviousPollDifference","racePollEventKey","buildRacePollPackages","raceComparableCandidateCount","rankRacePollPackages"]){
 const start=source.indexOf("    function "+name+"(");
 if(start<0)throw Error(name);
 const end=source.indexOf("\n    }",start)+6;
 functions+=source.slice(start,end)+"\n";
}
vm.runInContext(functions+`
const valid=polls.filter(isValidFirstRoundPollEvent);
const packages=rankRacePollPackages(buildRacePollPackages(valid),valid);
result={valid_ids:valid.map(e=>e.event_id),latest:deriveLatestFieldworkSummary(valid),coverage:derivePollCoverage(valid),packages:packages.map(p=>({
 key:p.key,pollster:p.pollster,ids:p.events.map(e=>e.event_id),
 selected:p.events[raceGlanceState.selectedHypothesisByPoll[p.key]].event_id,
 counts:p.events.map(e=>raceComparableCandidateCount(e,valid))})),
 comparisons:polls.filter(e=>FR27PollStudies.member(e)).map(e=>({id:e.event_id,
 strict:deriveComparableChange(valid,"Marine Le Pen",e.fieldwork_end,e),
 formatted:formatComparableChange(deriveComparableChange(valid,"Marine Le Pen",e.fieldwork_end,e)),
 previous:deriveRacePreviousPollDifference(valid,"Marine Le Pen",e)}))};
`,context);
process.stdout.write(JSON.stringify(context.result));
'''


VALIDATOR_SCRIPT = r'''
const fs=require("fs"), vm=require("vm");
const input=JSON.parse(fs.readFileSync(0,"utf8"));
const source=fs.readFileSync(input.page,"utf8").replace(/\r\n/g,"\n");
const start=source.indexOf("    function isValidFirstRoundPollEvent(");
if(start<0)throw Error("Missing homepage validator");
const end=source.indexOf("\n    }",start)+6;
const context={events:input.events,result:null};
vm.createContext(context);
vm.runInContext(source.slice(start,end)+`
if (${Boolean(input.nonfinite)}) {
  const base=events[0];
  const partial={...base,reported_total:98,completeness_status:"partial",partial_scenario:true,
    unreported_share:2,candidates:[{...base.candidates[0],score:50},{...base.candidates[1],score:48}]};
  events=[NaN,Infinity,-Infinity].flatMap(value=>[
    {...base,reported_total:value},
    {...base,candidates:[{...base.candidates[0],score:value},...base.candidates.slice(1)]},
    {...partial,unreported_share:value}
  ]);
}
result=events.map(isValidFirstRoundPollEvent);
`,context);
console.log(JSON.stringify(context.result));
'''


def python_accepts(event):
    try:
        contract.validate_poll_event(event)
    except contract.PollContractError:
        return False
    return True


class HomepageEligibilityTests(unittest.TestCase):
    @staticmethod
    def event(total=100, partial=False):
        event = {
            "round": "first_round", "pollster": "Test institute",
            "fieldwork_start": "2026-09-01", "fieldwork_end": "2026-09-02",
            "hypothesis": "Test scenario", "source_url": "https://example.test/poll",
            "candidates": [{"name": "Candidate A", "score": 50},
                           {"name": "Candidate B", "score": total - 50}],
            "reported_total": total, "completeness_status": "partial" if partial else "complete",
            "partial_scenario": partial, "unreported_share": 100 - total if partial else None,
        }
        event["scenario_key"] = contract.make_scenario_key(c["name"] for c in event["candidates"])
        event["event_id"] = contract.make_event_id(event["pollster"], event["fieldwork_start"],
                                                  event["fieldwork_end"], event["hypothesis"], event["source_url"])
        return event

    def assert_parity(self, cases, expected):
        self.assertEqual([python_accepts(event) for event in cases], expected)
        for page in ("index.html", "en/index.html"):
            with self.subTest(page=page):
                self.assertEqual(run_node(VALIDATOR_SCRIPT, {"page": page, "events": cases}), expected)

    def test_complete_total_boundaries_match_python(self):
        totals = [99, 100, 101, 102, 102.000001, 103, 98.999999, 98]
        self.assert_parity([self.event(total) for total in totals], [True] * 4 + [False] * 4)

    def test_partial_scenarios_and_completeness_flags_match_python(self):
        complete, partial = self.event(), self.event(98, partial=True)
        cases = [partial, self.event(50, partial=True),
                 dict(complete, partial_scenario=True), dict(complete, partial_scenario=0),
                 dict(complete, completeness_status="partial"), dict(complete, unreported_share=0),
                 dict(partial, partial_scenario=False), dict(partial, partial_scenario=1),
                 dict(partial, completeness_status="complete"), dict(partial, unreported_share=None),
                 dict(partial, unreported_share=3), dict(partial, reported_total=97),
                 self.event(99, partial=True), self.event(102, partial=True),
                 dict(complete, completeness_status="unknown"), dict(complete, reported_total=101)]
        self.assert_parity(cases, [True, True] + [False] * (len(cases) - 2))

    def test_malformed_events_and_candidates_remain_rejected(self):
        event = self.event()
        cases = [None, {}, [], "invalid", dict(event, round="second_round"),
                 dict(event, event_id=None), dict(event, scenario_key=None),
                 dict(event, candidates=None), dict(event, candidates=[]),
                 dict(event, candidates=event["candidates"][:1]), dict(event, reported_total="100")]
        for candidate in [None, {}, {"name": "", "score": 50}, {"name": " ", "score": 50},
                          {"name": 1, "score": 50}, {"name": "Candidate B", "score": 50},
                          {"name": "Candidate A", "score": -1}, {"name": "Candidate A", "score": "50"},
                          {"name": "Candidate A", "score": True}, {"name": "Candidate A", "score": None}]:
            cases.append(dict(event, candidates=[candidate, event["candidates"][1]]))
        self.assert_parity(cases, [False] * len(cases))

    def test_non_finite_numbers_remain_rejected(self):
        event = self.event()
        for number in (float("nan"), float("inf"), float("-inf")):
            self.assertFalse(python_accepts(dict(event, reported_total=number)))
            changed = copy.deepcopy(event)
            changed["candidates"][0]["score"] = number
            self.assertFalse(python_accepts(changed))
            self.assertFalse(python_accepts(dict(self.event(98, partial=True), unreported_share=number)))
        for page in ("index.html", "en/index.html"):
            with self.subTest(page=page):
                self.assertEqual(run_node(VALIDATOR_SCRIPT, {"page": page, "events": [event], "nonfinite": True}),
                                 [False] * 9)


class ReviewedStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.polls = read("polls.json")
        cls.binding = studies.load_binding()
        cls.ids = [m["event_id"] for m in cls.binding["members"]]
        cls.h2, cls.h1, cls.h3 = cls.ids
        cls.payload = explorer.build_poll_explorer(cls.polls)
        cls.wave = next(w for w in cls.payload["waves"] if w["wave_id"] == cls.binding["canonical_wave_id"])

    def test_exact_document_and_complete_event_pins(self):
        self.assertEqual(self.binding["source_document"]["sha256"],
                         "f97e63a028f809d62db0d961a4a271ef38581dac2fda6c58ec36f8be35ac8448")
        self.assertEqual([m["pdf_page"] for m in self.binding["members"]], [9, 5, 13])
        self.assertEqual(studies.object_digest(self.binding), studies.BINDING_SHA256)
        for event in self.polls:
            if event["event_id"] in self.ids:
                self.assertEqual(studies.object_digest(event), studies.reviewed_member(event)["object_sha256"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changed.json"
            changed = copy.deepcopy(self.binding)
            changed["canonical_pollster"] = "Other"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                studies.load_binding(path)
            with self.assertRaises(ValueError):
                studies.authenticate_document(path)

    def test_any_event_fact_drift_missing_member_duplicate_or_extra_member_fails_closed(self):
        event = next(e for e in self.polls if e["event_id"] == self.h1)
        for field, value in [("pollster", "Cluster17"), ("source_url", "https://example.test/"),
                             ("commissioner", "Politico"), ("unrelated_extra_field", True)]:
            changed = copy.deepcopy(event)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                studies.reviewed_member(changed)
        changed = copy.deepcopy(event)
        changed["candidates"][0]["score"] = 0
        with self.assertRaises(ValueError):
            studies.reviewed_member(changed)
        for values in [[e for e in self.polls if e["event_id"] != self.h1], self.polls + [event]]:
            with self.assertRaises(ValueError):
                studies.validate_study_membership(values)
        extra = copy.deepcopy(event)
        extra.update(event_id="new-unreviewed", pollster="Cluster17")
        with self.assertRaises(ValueError):
            studies.validate_study_membership(self.polls + [extra])
        unknown = dict(event, event_id="unreviewed")
        self.assertEqual(studies.projected_pollster(unknown), "Cluster 17")

    def test_single_reviewed_merge_reduces_wave_and_institute_census_by_one(self):
        raw_keys = {(e["pollster"],e["fieldwork_start"],e["fieldwork_end"],e.get("sample_size")) for e in self.polls}
        self.assertEqual(self.payload["metrics"]["wave_count"], len(raw_keys) - 1)
        self.assertEqual(self.payload["metrics"]["institute_count"], len({e["pollster"] for e in self.polls}) - 1)
        self.assertEqual(self.payload["metrics"]["scenario_count"], len(self.polls))
        self.assertEqual([s["event_id"] for s in self.wave["scenarios"]], self.ids)
        self.assertEqual(self.wave["selected_event_id"], self.h2)
        self.assertEqual(self.wave["source_pollster_labels"], ["Cluster 17", "Cluster17"])
        self.assertNotIn("Cluster 17", [i["name"] for i in self.payload["institutes"]])
        self.assertEqual(sum(w["fieldwork_end"] == "2026-10-22" and w["pollster"] == "Cluster17" for w in self.payload["waves"]), 1)

    def test_raw_observations_are_not_changed_by_projection(self):
        before = copy.deepcopy(self.polls)
        signals.build_poll_packages(self.polls)
        explorer.build_poll_explorer(self.polls)
        self.assertEqual(self.polls, before)
        source = {e["event_id"]: e for e in self.polls}
        for scenario in self.wave["scenarios"]:
            original = source[scenario["event_id"]]
            self.assertEqual(scenario["source_pollster"], original["pollster"])
            self.assertEqual(scenario["source_url"], original["source_url"])
            self.assertEqual(scenario["scenario_key"], original["scenario_key"])
            self.assertEqual([(c["published_candidate_name"],c["score"]) for c in scenario["candidates"]],
                             [(c["name"],c["score"]) for c in original["candidates"]])

    def test_candidate_history_has_one_study_and_observed_ranges_only(self):
        candidates = [{"candidate_id": c["candidate_id"], "candidate_name": c["candidate_name"]}
                      for c in self.payload["candidates"]]
        histories = signals.project_candidate_poll_history(candidates, self.polls)
        expected = {"marine-le-pen":(3,30.5,33,32.5), "jean-luc-melenchon":(3,18.5,19.5,19.5),
                    "raphael-glucksmann":(2,13,14,14), "edouard-philippe":(2,16,17,None),
                    "gabriel-attal":(1,12,12,12), "francois-hollande":(1,6.5,6.5,None)}
        for candidate_id, values in expected.items():
            rows = [row for row in histories[candidate_id]["observations"]
                    if row["fieldwork_end"] == "2026-10-22" and row["pollster"] == "Cluster17"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(tuple(rows[0][key] for key in ["hypothesis_count","range_min","range_max","selected_score"]), values)
            self.assertEqual(set(rows[0]["source_urls"]), set(self.wave["source_urls"]))

    def test_both_homepages_match_python_for_every_published_event(self):
        expected_ids = [event["event_id"] for event in self.polls if python_accepts(event)]
        self.assertEqual(len(expected_ids), len(self.polls))
        yougov_id = "fce9f5e59dc2dc1d26b53f7c8aa5551ab862c7ce78140cfe3ce0f5d36b5d46f1"
        yougov = next(event for event in self.polls if event["event_id"] == yougov_id)
        self.assertEqual((yougov["reported_total"], yougov["completeness_status"]), (102, "complete"))
        results = []
        for page in ["index.html", "en/index.html"]:
            result = run_node(HOMEPAGE_SCRIPT, {"page":page,"polls":self.polls})
            results.append(result)
            self.assertEqual(result["valid_ids"], expected_ids, page)
            self.assertIn(yougov_id, result["valid_ids"])
            self.assertEqual(result, run_node(HOMEPAGE_SCRIPT, {"page":page,"polls":self.polls}))
            python = signals.build_poll_packages(self.polls)
            self.assertEqual({p["key"]:p["ids"] for p in result["packages"]},
                             {p["package_key"]:[e["event_id"] for e in p["events"]] for p in python})
            python_by_key = {p["package_key"]: p for p in python}
            for package in result["packages"]:
                expected = python_by_key[package["key"]]
                self.assertEqual(package["counts"],
                                 [signals._comparable_candidate_count(event, self.polls) for event in expected["events"]])
                self.assertEqual(package["selected"], expected["selected_event"]["event_id"])
            ranked_python = sorted(python, key=lambda package: (
                package["fieldwork_end"], package["selected_comparable_candidate_count"]), reverse=True)
            self.assertEqual([p["key"] for p in result["packages"][:3]],
                             [p["package_key"] for p in ranked_python[:3]])
            # Restoring September's observation gives October's matching ballot 11 comparables.
            yougov_october_id = "a8b5d1cac12f97bb852a3da38204cd52aca008eed9be5a4e17938411bff29166"
            yougov_october = next(p for p in result["packages"] if yougov_october_id in p["ids"])
            self.assertEqual(yougov_october["counts"], [10, 0, 11, 0, 0])
            self.assertEqual(yougov_october["selected"], yougov_october_id)
            featured = next(p for p in result["packages"] if self.h2 in p["ids"])
            self.assertEqual(featured["ids"], self.ids)
            self.assertEqual(featured["counts"], [10,10,0])
            self.assertEqual(featured["selected"], self.h2)
            self.assertEqual(result["latest"]["pollsters"], ["Cluster17","Ipsos"])
            self.assertEqual(result["coverage"]["count"], 10)
            self.assertEqual([p["pollster"] for p in result["packages"][:3]], ["Ipsos","Cluster17","Harris"])
            h1 = next(c for c in result["comparisons"] if c["id"] == self.h1)
            self.assertEqual(h1["strict"]["deltas"], [2])
            self.assertTrue(h1["formatted"]["meta"].endswith("Cluster17"))
            self.assertEqual(h1["previous"]["classification"], "POLLSTER_CHANGED")
            self.assertEqual(h1["previous"]["delta"], -2)
        for key in ("valid_ids", "latest", "coverage", "packages"):
            self.assertEqual(results[0][key], results[1][key], key)

    def test_browser_authentication_rechecks_mutated_objects_and_complete_membership(self):
        script = r'''
require("./assets/poll-study-bindings.js");
const p=require("./polls.json"), h=p.find(e=>e.event_id.startsWith("2b452"));
FR27PollStudies.verifyCollection(p);
const errors=[];
try { h.source_url+="?changed"; FR27PollStudies.pollster(h); } catch(e){errors.push(e.message);}
try { FR27PollStudies.verifyCollection(p.filter(e=>!e.event_id.startsWith("26e5f"))); } catch(e){errors.push(e.message);}
console.log(JSON.stringify(errors));
'''
        self.assertEqual(len(run_node(script)), 2)
        self.assertEqual((ROOT/"assets/poll-study-bindings.js").read_text(encoding="utf-8"), studies.browser_script())

    def test_candidate_history_change_is_limited_to_the_thirteen_study_participants(self):
        candidates = read("candidate_signals.json")["candidates"]
        current = signals.project_candidate_poll_history(candidates, self.polls)
        raw_key = lambda e: (e["pollster"], e["fieldwork_start"], e["fieldwork_end"], e.get("sample_size"))
        with patch.object(signals, "study_package_key", raw_key), patch.object(signals, "projected_pollster", lambda e:e["pollster"]), patch.object(signals, "scenario_order", lambda e:0):
            previous = signals.project_candidate_poll_history(candidates, self.polls)
        affected = {c["candidate_id"] for s in self.wave["scenarios"] for c in s["candidates"]}
        changed = {key for key in current if current[key] != previous[key]}
        self.assertEqual(changed, affected)
        self.assertEqual(len(changed), 13)
        reduced = [key for key in current if current[key]["observation_count"] != previous[key]["observation_count"]]
        self.assertEqual(len(reduced), 9)
        for key in reduced:
            self.assertEqual(current[key]["observation_count"], previous[key]["observation_count"]-1)
        for key in current:
            unaffected = lambda h:[r for r in h["observations"] if not (r["fieldwork_end"]=="2026-10-22" and r["pollster"] in ("Cluster17","Cluster 17"))]
            self.assertEqual(unaffected(current[key]), unaffected(previous[key]))

    def test_homepage_pair_comparisons_share_the_authenticated_study(self):
        script = r'''
const fs=require("fs"), vm=require("vm");
const input=JSON.parse(fs.readFileSync(0,"utf8"));
const source=fs.readFileSync(input.page,"utf8").replace(/\r\n/g,"\n");
const context={polls:input.polls,URL, result:null,collator:new Intl.Collator("fr")};
vm.createContext(context);
vm.runInContext(fs.readFileSync("assets/poll-study-bindings.js","utf8"),context);
let code="";
for(const name of ["safeSourceUrl","normalizeSourceKey","recordSignature","normalizeEvent","compareHypotheses","pairKey","findComparisons","groupPollWaves"]){
 const pad=name==="safeSourceUrl"?"    ":"      ";
 const start=source.indexOf(pad+"function "+name+"(");
 if(start<0)throw Error(name);
 const end=source.indexOf("\n"+pad+"}",start)+pad.length+2;
 code+=source.slice(start,end)+"\n";
}
vm.runInContext(code+"result=groupPollWaves(polls).filter(w=>w.fieldworkEnd==='2026-10-22'&&w.pollster==='Cluster17');",context);
console.log(JSON.stringify(context.result));
'''
        for page in ["index.html","en/index.html"]:
            result = run_node(script,{"page":page,"polls":self.polls})
            self.assertEqual(len(result),1)
            self.assertEqual([h["hLabel"] for h in result[0]["hypotheses"]],["H2","H1","H3"])
            self.assertGreaterEqual(len(result[0]["comparisons"]),1)

    def test_event_fragments_open_their_parent_scenario(self):
        script = r'''
const fs=require("fs"),vm=require("vm");
const source=fs.readFileSync("assets/poll-page.js","utf8");
const start=source.indexOf("  const openFromHash = ");
const end=source.indexOf("\n  };",start)+5;
let opened=null;
const parent={id:"scenario-3"}, anchor={closest:()=>parent};
const context={window:{location:{hash:"#scenario-"+"a".repeat(64)}},document:{getElementById:()=>anchor},openScenario:(node)=>opened=node.id};
vm.createContext(context);
vm.runInContext(source.slice(start,end)+";openFromHash();",context);
console.log(JSON.stringify(opened));
'''
        self.assertEqual(run_node(script),"scenario-3")

    def test_canonical_and_legacy_fragments_and_route_indexing(self):
        from lxml import html
        canonical = ROOT / pages.page_file_from_url(self.wave["page_path_fr"])
        doc = html.fromstring(canonical.read_text(encoding="utf-8"))
        self.assertIn(self.h2, doc.get_element_by_id("scenario-1").text_content())
        for event_id in self.ids:
            anchor = doc.get_element_by_id("scenario-" + event_id)
            self.assertIn(event_id, anchor.getparent().text_content())
        manifest = read("poll_pages_manifest.json")
        self.assertEqual(manifest["compatibility_page_count"], 2)
        self.assertNotIn(self.binding["compatibility"]["wave_id"], [p["wave_id"] for p in manifest["pages"]])
        for language in ["fr", "en"]:
            legacy = self.binding["compatibility"][f"page_path_{language}"]
            target = "https://france2027.app" + self.wave[f"page_path_{language}"]
            doc = html.fromstring((ROOT/pages.page_file_from_url(legacy)).read_text(encoding="utf-8"))
            self.assertEqual(doc.xpath('//link[@rel="canonical"]/@href'), [target])
            self.assertEqual(doc.xpath('//meta[@name="robots"]/@content'), ["noindex,follow"])
            self.assertEqual({x for x in doc.xpath('//link[@rel="alternate"]/@hreflang')}, {"fr","en","x-default"})
            for index,event_id in enumerate(self.binding["compatibility"]["legacy_scenario_event_ids"],1):
                self.assertEqual(doc.get_element_by_id(f"scenario-{index}").xpath('.//a/@href'), [target+"#scenario-"+event_id])
            registry = read("route_registry.json")
            self.assertIn(legacy, [p["path"] for p in registry["compatibility_pages"]])
            self.assertNotIn(legacy, [p["path"] for p in registry["routes"]])
            self.assertNotIn("https://france2027.app"+legacy, (ROOT/"sitemap-polls.xml").read_text(encoding="utf-8"))
        # Lab's exact-ballot series now consumes the same canonical institute.
        source = (ROOT/"assets/polling-lab.js").read_text(encoding="utf-8")
        start = source.index("  function sharedComparableSeriesKey(")
        end = source.index("\n  }", start)+4
        key = run_node(source[start:end]+"\nconsole.log(JSON.stringify(sharedComparableSeriesKey("+json.dumps(self.wave)+","+json.dumps(self.wave["scenarios"][1])+")));" )
        self.assertEqual(key, "Cluster17\0"+self.wave["scenarios"][1]["scenario_key"])


if __name__ == "__main__":
    unittest.main()
