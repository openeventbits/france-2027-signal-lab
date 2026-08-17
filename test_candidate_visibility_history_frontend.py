from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HISTORY_JS = (
    ROOT
    / "assets"
    / "candidate-visibility-history.js"
)
INDEX = ROOT / "index.html"


def dates():
    start = date(2026, 7, 19)
    return [
        (
            start
            + timedelta(days=offset)
        ).isoformat()
        for offset in range(29)
    ]


def candidate_identities():
    return [
        {
            "candidate_id": "alice",
            "candidate_name": "Alice",
        },
        {
            "candidate_id": "bob",
            "candidate_name": "Bob",
        },
    ]


def payload():
    day_values = dates()

    campaign_denominators = [
        {
            "date": current_date,
            "record_count": 2,
            "publisher_count": 2,
        }
        for current_date in day_values
    ]

    general_denominators = [
        {
            "date": current_date,
            "record_count": (
                0 if index == 4 else 1
            ),
            "publisher_count": (
                0 if index == 4 else 1
            ),
        }
        for index, current_date
        in enumerate(day_values)
    ]

    def campaign_series(
        count,
        share,
    ):
        return [
            {
                "date": current_date,
                "record_count": count,
                "share": share,
                "publisher_count": (
                    1 if count else 0
                ),
            }
            for current_date
            in day_values
        ]

    alice_general = []
    bob_general = []

    for index, current_date in enumerate(
        day_values
    ):
        if index == 4:
            alice_general.append(
                {
                    "date": current_date,
                    "record_count": 0,
                    "share": None,
                    "publisher_count": 0,
                }
            )
            bob_general.append(
                {
                    "date": current_date,
                    "record_count": 0,
                    "share": None,
                    "publisher_count": 0,
                }
            )
        else:
            alice_general.append(
                {
                    "date": current_date,
                    "record_count": 0,
                    "share": 0.0,
                    "publisher_count": 0,
                }
            )
            bob_general.append(
                {
                    "date": current_date,
                    "record_count": 1,
                    "share": 1.0,
                    "publisher_count": 1,
                }
            )

    return {
        "schema_version": "1.0",
        "period": {
            "start_date": day_values[0],
            "end_date": day_values[-1],
            "days": 29,
            "data_as_of": day_values[-1],
            "day_boundary": "UTC",
            "current_utc_day_excluded": True,
        },
        "methodology": {
            "source": (
                "news_wire.json:"
                "candidate_watch"
            ),
            "primary_scopes": [
                "election",
                "campaign",
            ],
            "general_scope": "general",
            "metric": (
                "candidate_share_of_lane_records"
            ),
            "candidate_linkage": (
                "published_candidate_matches"
            ),
            "not_measures": [
                "sentiment",
                "approval",
                "electoral support",
                "voting intention",
            ],
        },
        "lanes": {
            "campaign_attention": {
                "daily_denominators": (
                    campaign_denominators
                ),
            },
            "general_visibility": {
                "daily_denominators": (
                    general_denominators
                ),
            },
        },
        "candidates": [
            {
                "candidate_id": "alice",
                "candidate_name": "Alice",
                "campaign_attention": {
                    "daily_series": (
                        campaign_series(
                            1,
                            0.5,
                        )
                    ),
                },
                "general_visibility": {
                    "daily_series": (
                        alice_general
                    ),
                },
            },
            {
                "candidate_id": "bob",
                "candidate_name": "Bob",
                "campaign_attention": {
                    "daily_series": (
                        campaign_series(
                            0,
                            0.0,
                        )
                    ),
                },
                "general_visibility": {
                    "daily_series": (
                        bob_general
                    ),
                },
            },
        ],
    }


def run_node(expression, input_payload):
    node = shutil.which("node")

    if node is None:
        raise unittest.SkipTest(
            "Node.js is required for "
            "Candidate Visibility History "
            "frontend tests"
        )

    script = r'''
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(
  "assets/candidate-visibility-history.js",
  "utf8"
);

const input = JSON.parse(
  fs.readFileSync(0, "utf8")
);

const windowObject = {
  fetch: undefined
};

const context = {
  console,
  Date,
  Math,
  Map,
  Set,
  Object,
  Array,
  Number,
  String,
  Boolean,
  JSON,
  Promise,
  window: windowObject
};

vm.runInNewContext(
  source,
  context
);

const api =
  context.window
    .France2027CandidateVisibilityHistory;

(async () => {
  const result = await eval(
    input.expression
  );

  process.stdout.write(
    JSON.stringify(result)
  );
})().catch(error => {
  console.error(error);
  process.exit(1);
});
'''

    completed = subprocess.run(
        [node, "-e", script],
        input=json.dumps(
            {
                "expression": expression,
                "payload": input_payload,
            }
        ),
        cwd=ROOT,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )

    return json.loads(
        completed.stdout
    )


def normalize_result(
    value,
    expected=None,
):
    expression = (
        "api.normalize("
        "input.payload.value, "
        "input.payload.expected"
        ")"
    )

    return run_node(
        expression,
        {
            "value": value,
            "expected": expected,
        },
    )


class CandidateVisibilityHistoryFrontendTests(
    unittest.TestCase
):
    def test_valid_schema_is_ready(self):
        result = normalize_result(
            payload(),
            candidate_identities(),
        )

        self.assertEqual(
            result["status"],
            "ready",
        )
        self.assertIsNone(
            result["reason"]
        )
        self.assertEqual(
            result["payload"][
                "schema_version"
            ],
            "1.0",
        )

    def test_wrong_schema_is_rejected(self):
        value = payload()
        value["schema_version"] = "9.9"

        result = normalize_result(
            value,
            candidate_identities(),
        )

        self.assertEqual(
            result,
            {
                "status": "unavailable",
                "payload": None,
                "reason": "invalid_payload",
            },
        )

    def test_unknown_top_level_key_is_rejected(self):
        value = payload()
        value["generated_at"] = (
            "2026-08-17T12:00:00Z"
        )

        result = normalize_result(
            value,
            candidate_identities(),
        )

        self.assertEqual(
            result["reason"],
            "invalid_payload",
        )

    def test_incomplete_period_is_rejected(self):
        value = payload()

        value["period"]["days"] = 28

        result = normalize_result(
            value,
            candidate_identities(),
        )

        self.assertEqual(
            result["reason"],
            "invalid_payload",
        )

    def test_wrong_end_date_is_rejected(self):
        value = payload()

        value["period"]["end_date"] = (
            "2026-08-15"
        )

        result = normalize_result(
            value,
            candidate_identities(),
        )

        self.assertEqual(
            result["reason"],
            "invalid_payload",
        )

    def test_missing_daily_date_is_rejected(self):
        value = payload()

        value["lanes"][
            "campaign_attention"
        ]["daily_denominators"][7][
            "date"
        ] = "2026-09-01"

        result = normalize_result(
            value,
            candidate_identities(),
        )

        self.assertEqual(
            result["reason"],
            "invalid_payload",
        )

    def test_duplicate_daily_date_is_rejected(self):
        value = payload()

        value["candidates"][0][
            "campaign_attention"
        ]["daily_series"][8][
            "date"
        ] = value["candidates"][0][
            "campaign_attention"
        ]["daily_series"][7][
            "date"
        ]

        result = normalize_result(
            value,
            candidate_identities(),
        )

        self.assertEqual(
            result["reason"],
            "invalid_payload",
        )

    def test_candidate_mismatch_is_rejected(self):
        value = payload()

        expected = candidate_identities()
        expected[1][
            "candidate_name"
        ] = "Changed Bob"

        result = normalize_result(
            value,
            expected,
        )

        self.assertEqual(
            result["reason"],
            "candidate_mismatch",
        )

    def test_backend_order_with_accented_names_is_accepted(self):
        value = payload()

        value["candidates"] = [
            deepcopy(value["candidates"][0]),
            deepcopy(value["candidates"][1]),
        ]

        value["candidates"][0][
            "candidate_id"
        ] = "yannick-jadot"
        value["candidates"][0][
            "candidate_name"
        ] = "Yannick Jadot"

        value["candidates"][1][
            "candidate_id"
        ] = "edouard-philippe"
        value["candidates"][1][
            "candidate_name"
        ] = "Édouard Philippe"

        expected = [
            {
                "candidate_id": "yannick-jadot",
                "candidate_name": "Yannick Jadot",
            },
            {
                "candidate_id": "edouard-philippe",
                "candidate_name": "Édouard Philippe",
            },
        ]

        result = normalize_result(
            value,
            expected,
        )

        self.assertEqual(
            result["status"],
            "ready",
        )
        self.assertIsNone(
            result["reason"]
        )


    def test_candidate_order_mismatch_is_rejected(self):
        value = payload()
        value["candidates"].reverse()

        result = normalize_result(
            value,
            None,
        )

        self.assertEqual(
            result["reason"],
            "invalid_payload",
        )

    def test_positive_denominator_preserves_zero_share(self):
        result = normalize_result(
            payload(),
            candidate_identities(),
        )

        point = result["payload"][
            "candidates"
        ][1][
            "campaign_attention"
        ]["daily_series"][0]

        self.assertEqual(
            point["record_count"],
            0,
        )
        self.assertEqual(
            point["share"],
            0.0,
        )

    def test_zero_denominator_requires_null_share(self):
        value = payload()

        value["candidates"][0][
            "general_visibility"
        ]["daily_series"][4][
            "share"
        ] = 0.0

        result = normalize_result(
            value,
            candidate_identities(),
        )

        self.assertEqual(
            result["reason"],
            "invalid_payload",
        )

    def test_incorrect_share_is_rejected(self):
        value = payload()

        value["candidates"][0][
            "campaign_attention"
        ]["daily_series"][0][
            "share"
        ] = 0.499

        result = normalize_result(
            value,
            candidate_identities(),
        )

        self.assertEqual(
            result["reason"],
            "invalid_payload",
        )

    def test_campaign_and_general_denominators_remain_separate(self):
        result = normalize_result(
            payload(),
            candidate_identities(),
        )

        campaign = result["payload"][
            "lanes"
        ][
            "campaign_attention"
        ][
            "daily_denominators"
        ][4]

        general = result["payload"][
            "lanes"
        ][
            "general_visibility"
        ][
            "daily_denominators"
        ][4]

        self.assertEqual(
            campaign["record_count"],
            2,
        )
        self.assertEqual(
            general["record_count"],
            0,
        )

    def test_publisher_count_cannot_exceed_candidate_count(self):
        value = payload()

        value["candidates"][0][
            "campaign_attention"
        ]["daily_series"][0][
            "publisher_count"
        ] = 2

        result = normalize_result(
            value,
            candidate_identities(),
        )

        self.assertEqual(
            result["reason"],
            "invalid_payload",
        )

    def test_invalid_expected_universe_is_bounded(self):
        result = normalize_result(
            payload(),
            [],
        )

        self.assertEqual(
            result,
            {
                "status": "unavailable",
                "payload": None,
                "reason": (
                    "invalid_candidate_universe"
                ),
            },
        )

    def test_load_is_fail_soft_on_http_error(self):
        expression = r'''
api.load(
  "candidate_visibility_history.json",
  input.payload.expected,
  async () => ({
    ok: false,
    json: async () => ({})
  })
)
'''

        result = run_node(
            expression,
            {
                "expected": (
                    candidate_identities()
                ),
            },
        )

        self.assertEqual(
            result["status"],
            "unavailable",
        )
        self.assertEqual(
            result["reason"],
            "http_error",
        )

    def test_load_is_fail_soft_on_fetch_failure(self):
        expression = r'''
api.load(
  "candidate_visibility_history.json",
  input.payload.expected,
  async () => {
    throw new Error("boom");
  }
)
'''

        result = run_node(
            expression,
            {
                "expected": (
                    candidate_identities()
                ),
            },
        )

        self.assertEqual(
            result["status"],
            "unavailable",
        )
        self.assertEqual(
            result["reason"],
            "fetch_failed",
        )

    def test_load_uses_no_store_and_returns_ready(self):
        expression = r'''
(() => {
  let seenUrl = null;
  let seenCache = null;

  return api.load(
    "candidate_visibility_history.json",
    input.payload.expected,
    async (url, options) => {
      seenUrl = url;
      seenCache = options.cache;

      return {
        ok: true,
        json: async () => input.payload.value
      };
    }
  ).then(result => ({
    status: result.status,
    reason: result.reason,
    seenUrl,
    seenCache
  }));
})()
'''

        result = run_node(
            expression,
            {
                "value": payload(),
                "expected": (
                    candidate_identities()
                ),
            },
        )

        self.assertEqual(
            result,
            {
                "status": "ready",
                "reason": None,
                "seenUrl": (
                    "candidate_visibility_history.json"
                ),
                "seenCache": "no-store",
            },
        )

    def test_index_registers_history_loader_before_hybrid(self):
        index = INDEX.read_text(
            encoding="utf-8"
        )

        history = index.index(
            'src="assets/candidate-visibility-history.js"'
        )
        hybrid = index.index(
            'src="assets/hybrid-dashboard.js"'
        )

        self.assertLess(
            history,
            hybrid,
        )

    def test_hybrid_consumes_history_after_candidate_signals(self):
        hybrid = (
            ROOT
            / "assets"
            / "hybrid-dashboard.js"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "France2027CandidateVisibilityHistory",
            hybrid,
        )
        self.assertIn(
            "candidateVisibilityHistory",
            hybrid,
        )
        self.assertEqual(
            hybrid.count(
                '"candidate_visibility_history.json"'
            ),
            1,
        )

        candidate_request = hybrid.index(
            "const candidateSignalsRequest ="
        )
        history_request = hybrid.index(
            "const candidateVisibilityHistoryRequest ="
        )
        history_load = hybrid.index(
            '"candidate_visibility_history.json"'
        )

        self.assertLess(
            candidate_request,
            history_request,
        )
        self.assertLess(
            history_request,
            history_load,
        )
        self.assertIn(
            "Promise.resolve(candidateSignalsRequest)",
            hybrid,
        )
        self.assertIn(
            "candidateSignalsState.candidates",
            hybrid,
        )


if __name__ == "__main__":
    unittest.main()