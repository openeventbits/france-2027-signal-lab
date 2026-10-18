import copy
import unittest
from history_test_support import HistoryCases


class PolymarketHistoryTests(HistoryCases, unittest.TestCase):
    provider = "polymarket"
    identity = "yes_token_id"
    metric = "implied_probability"
    mapping_file = "polymarket_candidate_markets.json"
    changed_identity = "123456789"

    def run_collection(self, directory, fetch, mode="backfill", previous=None):
        import json
        from pathlib import Path
        from candidate_history import encode
        from history_test_support import ROOT
        output = Path(directory) / "history.json"
        if previous is not None: output.write_bytes(encode(previous))
        snapshot = Path(directory) / "snapshot.json"; snapshot.write_bytes(encode(self.snapshot))
        return self.builder.collect(output, mode=mode, fetch=fetch, snapshot_path=snapshot,
            mapping_path=ROOT / self.mapping_file, registry_path=ROOT / "candidate_candidacy_status.json")

    def test_source_parse_order_duplicates_and_daily_latest(self):
        from candidate_history import roll_points
        t = int(self.anchor.timestamp()) - 86400
        points = self.builder.parse_source({"history": [{"t":t,"p":0.4},{"t":t-10,"p":0.3},{"t":t,"p":0.4}]}, t-20, t)
        self.assertEqual(len(points), 2)
        daily = roll_points([], points, anchor=self.anchor, value_field=self.metric, probability=True)
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0][self.metric], 0.4)
        with self.assertRaises(ValueError): self.builder.parse_source({"history":[{"t":t,"p":0.3},{"t":t,"p":0.4}]},t-1,t)

    def test_source_sampling_edges_are_clipped_without_backdating(self):
        result=self.builder.parse_source({"history":[{"t":0,"p":0.1},{"t":2,"p":0.2},{"t":4,"p":0.3}]},1,3)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["observed_at"],"1970-01-01T00:00:02Z")

    def test_source_bounds_and_schema(self):
        for response in ({}, {"history":None}, {"history":[{"t":False,"p":0.3}]},
                         {"history":[{"t":1,"p":1.1}]}, {"history":[{"t":1,"p":-0.1}]},
                         {"history":[{"t":-1,"p":0.3}]}, {"history":[{"t":1,"p":"0.3"}]}):
            with self.assertRaises(ValueError): self.builder.parse_source(response,0,2)

    def test_backfill_exact_pinned_tokens_and_snapshot_parity(self):
        import tempfile
        from history_test_support import ROOT
        calls=[]
        def fetch(token,start,end):
            calls.append((token,start,end))
            return {"history":[{"t":end-86400,"p":0.421},{"t":end,"p":0.9}]}
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            result,report=self.run_collection(directory,fetch)
        self.assertEqual({c[0] for c in calls},{r["outcome_id"] for r in self.mapping["markets"]})
        self.assertGreater(len(calls),len(self.mapping["markets"]))
        self.assertTrue(all(end-start<=7*86400 for _,start,end in calls))
        self.validate(result,mapping=self.mapping,candidate_ids=self.ids,snapshot=self.snapshot)
        self.assertTrue(all(r["points"][-1]["source"]=="fr27_snapshot" for r in result["candidates"] if r["points"]))
        self.assertEqual(report["fidelity_minutes"],1440)

    def test_latest_source_price_and_frozen_snapshot_are_both_preserved(self):
        from candidate_history import iso
        source={self.cid:[dict(self.point(-1,0.421))]}
        result=self.mod.build_history(self.snapshot,self.mapping,self.ids,source_points=source)
        row=next(r for r in result["candidates"] if r["candidate_id"]==self.cid)
        self.assertEqual(row["latest_source_point"]["implied_probability"],0.421)
        self.assertEqual(row["points"][-1]["source"],"fr27_snapshot")
        self.assertEqual(row["points"][-1]["observed_at"],self.snapshot["observed_at"])

    def test_same_timestamp_source_and_snapshot_are_not_conflated(self):
        result=self.mod.build_history(self.snapshot,self.mapping,self.ids,
            source_points={self.cid:[self.point(0,0.9)]})
        row=next(r for r in result["candidates"] if r["candidate_id"]==self.cid)
        self.assertEqual(row["latest_source_point"]["implied_probability"],0.9)
        self.assertEqual(row["points"][-1]["implied_probability"],0.3)
        self.assertEqual(row["points"][-1]["source"],"fr27_snapshot")

    def test_incremental_overlap_and_no_repeat_download(self):
        import tempfile
        from history_test_support import ROOT
        from candidate_history import iso
        calls=[]
        def fetch(token,start,end): calls.append((token,start,end)); return {"history":[]}
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            initial,_=self.run_collection(directory,fetch)
            calls.clear()
            same,_=self.run_collection(directory,fetch,mode="incremental",previous=initial)
            self.assertEqual(calls,[])
            self.advance(days=1)
            updated,_=self.run_collection(directory,fetch,mode="incremental",previous=same)
            self.assertTrue(calls)
            self.assertTrue(all(end-start<3*86400 for _,start,end in calls))
            self.assertEqual(updated["observed_at"],self.snapshot["observed_at"])

    def test_network_failure_preserves_history_and_current_snapshot(self):
        import tempfile
        from pathlib import Path
        from candidate_history import encode
        from history_test_support import ROOT
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output=Path(directory)/"history.json";output.write_bytes(encode(self.history));before=output.read_bytes()
            current=(ROOT/"candidate_polymarket.json").read_bytes()
            def fail(*args): raise OSError("injected network failure")
            with self.assertRaises(OSError): self.run_collection(directory,fail,previous=self.history)
            self.assertEqual(output.read_bytes(),before)
            self.assertEqual((ROOT/"candidate_polymarket.json").read_bytes(),current)

    def test_http_retries_bounds_request_token_and_no_auth(self):
        import io,json
        from urllib.error import HTTPError
        from urllib.parse import parse_qs,urlsplit
        from unittest import mock
        token=self.mapping["markets"][0]["outcome_id"]
        response=mock.MagicMock();response.__enter__.return_value=response;response.status=200
        response.read.return_value=b'{"history":[]}'
        failures=[HTTPError(self.builder.API_URL,429,"rate limit",{},None),
                  HTTPError(self.builder.API_URL,503,"busy",{},None),response]
        opener=mock.Mock(side_effect=failures);sleep=mock.Mock();counts={"request_count":0}
        self.assertEqual(self.builder.fetch_history(token,1,2,opener=opener,sleep=sleep,counters=counts),{"history":[]})
        self.assertEqual(counts["request_count"],3)
        request=opener.call_args.args[0];query=parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(query,{"market":[token],"startTs":["1"],"endTs":["2"],"fidelity":["1440"]})
        self.assertEqual(opener.call_args.kwargs["timeout"],20)
        self.assertFalse(request.has_header("Authorization"))
        self.assertEqual(sleep.call_count,2)

    def test_terminal_http_network_malformed_and_oversized_response(self):
        from urllib.error import HTTPError,URLError
        from unittest import mock
        token=self.mapping["markets"][0]["outcome_id"]
        for error,attempts in [(HTTPError(self.builder.API_URL,400,"bad",{},None),1),
                               (TimeoutError(),3),(URLError("offline"),3)]:
            opener=mock.Mock(side_effect=error)
            with self.assertRaises(ValueError): self.builder.fetch_history(token,1,2,opener=opener,sleep=lambda _:None)
            self.assertEqual(opener.call_count,attempts)
        for body in (b'not-json', b'x'*(self.builder.MAX_BYTES+1)):
            response=mock.MagicMock();response.__enter__.return_value=response;response.status=200;response.read.return_value=body
            with self.assertRaises(ValueError): self.builder.fetch_history(token,1,2,opener=lambda *a,**k:response)

    def test_history_manifest_lanes_and_corruption_block_publication(self):
        import json,tempfile
        from pathlib import Path
        from unittest import mock
        import build_publication_manifest as manifest
        from candidate_history import encode
        from history_test_support import ROOT
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root=Path(directory)
            for names in manifest.LANE_FILES.values():
                for name in names:
                    (root/name).write_bytes((ROOT/name).read_bytes())
            for provider,mapping in (("polymarket","polymarket_candidate_markets.json"),
                                     ("youtube","youtube_candidate_channels.json"),("bluesky","bluesky_candidate_accounts.json")):
                import importlib
                module=importlib.import_module("candidate_"+provider+"_history")
                snapshot=json.loads((root/("candidate_"+provider+".json")).read_text(encoding="utf-8"))
                config=json.loads((root/mapping).read_text(encoding="utf-8"))
                built=module.build_history(snapshot,config,{r["candidate_id"] for r in snapshot["candidates"]})
                (root/("candidate_"+provider+"_history.json")).write_bytes(encode(built))
                lane,_=manifest._build_lane(root,"candidate_"+provider+"_history")
                self.assertTrue(lane["valid"]);self.assertEqual(lane["record_count"],len(self.ids))
                self.assertEqual(len(lane["related_files"]),2)
            (root/"candidate_youtube_history.json").write_text('{}')
            with self.assertRaises(manifest.ManifestError): manifest.build_manifest(root,published_at=self.snapshot["observed_at"])

    def test_workflow_gates_network_and_stages_all_histories(self):
        from history_test_support import ROOT
        workflow=(ROOT/".github/workflows/publish-candidate-family.yml").read_text(encoding="utf-8")
        start=workflow.index('- name: Update candidate provider histories');end=workflow.index('- name: Build and validate candidate publication')
        step=workflow[start:end]
        self.assertIn("github.event_name == 'schedule'",step)
        self.assertIn("github.event_name == 'workflow_dispatch'",step)
        self.assertIn('build_candidate_polymarket_history.py --incremental',step)
        for provider in ("polymarket","youtube","bluesky"):
            self.assertGreaterEqual(workflow.count('candidate_'+provider+'_history.json'),5)
            self.assertIn('build_candidate_'+provider+'_history.py --check',workflow)
